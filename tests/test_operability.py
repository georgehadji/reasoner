"""Operational readiness: monitoring signals that actually fire.

Each of these was either absent or silently broken:
  - Alertmanager could not parse its config, so no alert could ever be delivered.
  - No rule referenced the scrape target's own health, so a dead backend was silent.
  - The Postgres "free connections" gauge was inverted, so the critical
    pool-exhaustion alert fired on an idle pool and stayed quiet on a full one.
  - reasoner_quota_exceeded_total was defined and alerted on but never
    incremented, so the abuse tripwire could never fire.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[1]
MONITORING = REPO_ROOT / "docs" / "monitoring"


def _load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class TestAlertmanagerConfigIsLoadable:
    @pytest.fixture(scope="class")
    def config(self):
        return _load(MONITORING / "alertmanager.yml")

    def test_has_no_unexpanded_env_vars(self, config):
        """Alertmanager performs no env expansion — `${VAR}` is used literally."""
        raw = (MONITORING / "alertmanager.yml").read_text(encoding="utf-8")
        active = [
            line for line in raw.splitlines()
            if "${" in line and not line.strip().startswith("#")
        ]
        assert not active, f"unexpanded env vars in active config: {active}"

    def test_every_route_receiver_is_defined(self, config):
        """An undefined receiver is a hard startup failure."""
        defined = {r["name"] for r in config["receivers"]}
        route = config["route"]
        referenced = {route["receiver"]}
        referenced |= {r["receiver"] for r in route.get("routes", [])}
        assert referenced <= defined, f"undefined receivers: {referenced - defined}"

    def test_webhook_receivers_carry_no_slack_only_fields(self, config):
        """`title`/`text` belong to slack_configs; Alertmanager rejects them here."""
        for receiver in config["receivers"]:
            for webhook in receiver.get("webhook_configs") or []:
                assert "title" not in webhook and "text" not in webhook, (
                    f"receiver {receiver['name']}: slack-only fields in webhook_configs"
                )

    def test_no_receiver_posts_back_into_alertmanager(self, config):
        """The default receiver used to POST to Alertmanager's own alerts API."""
        for receiver in config["receivers"]:
            for webhook in receiver.get("webhook_configs") or []:
                assert "/api/v2/alerts" not in webhook.get("url", ""), (
                    f"receiver {receiver['name']} feeds alerts back into Alertmanager"
                )

    def test_referenced_template_dir_exists_if_declared(self, config):
        """A templates glob pointing at nothing is a needless startup risk."""
        if config.get("templates"):
            assert (MONITORING / "templates").exists(), (
                "alertmanager.yml declares templates but no templates dir is shipped"
            )


class TestAlertRules:
    @pytest.fixture(scope="class")
    def rules(self):
        return _load(MONITORING / "alerts.yml")["groups"][0]["rules"]

    @pytest.fixture(scope="class")
    def prometheus_jobs(self):
        cfg = _load(MONITORING / "prometheus.yml")
        return {j["job_name"] for j in cfg["scrape_configs"]}

    def test_backend_liveness_is_alerted(self, rules):
        """Without this, a dead backend produces silence, not a page."""
        names = {r["alert"] for r in rules}
        assert "BackendDown" in names
        assert "BackendMetricsAbsent" in names

    def test_liveness_rule_targets_a_real_scrape_job(self, rules, prometheus_jobs):
        """A rule naming a job that isn't scraped can never fire."""
        for rule in rules:
            for job in re.findall(r'job="([^"]+)"', rule["expr"]):
                assert job in prometheus_jobs, (
                    f"{rule['alert']} references job {job!r}, "
                    f"but prometheus.yml scrapes {sorted(prometheus_jobs)}"
                )

    def test_alerted_metrics_are_actually_incremented(self, rules):
        """A metric that is defined but never written is a permanently silent alert.

        reasoner_quota_exceeded_total was defined, alerted on as the abuse
        tripwire (QuotaExceededSpike), and incremented nowhere. This
        cross-references every metric named in an alert `expr:` against the
        code that writes it, so "defined but never incremented" fails CI
        rather than shipping as a silent alert.
        """
        import reasoner.infrastructure.metrics as metrics_mod

        identifier_for = {}
        for attr in dir(metrics_mod):
            metric = getattr(metrics_mod, attr)
            name = getattr(metric, "_name", None)
            if name:
                identifier_for[name] = attr

        exprs = " ".join(r["expr"] for r in rules)
        referenced = set(
            re.findall(r"\b(reasoner_[a-z_]+?)(?:_total|_bucket|_sum|_count)?\b", exprs)
        )

        # Pure-Python search rather than shelling out to `grep`: it is not on
        # PATH on every dev machine (Windows in particular), and this needs
        # to run identically in CI and locally.
        #
        # A metric can be written two ways: directly (`IDENTIFIER.inc()`
        # somewhere outside infrastructure/metrics.py), or through the
        # core-owned hook pattern (core/degrade.py, core/ports/metrics_port.py)
        # where the only line naming the identifier *is* the `.inc()`/`.set()`
        # call itself, e.g. `set_quota_exceeded_counter(lambda tier:
        # REASONER_QUOTA_EXCEEDED_TOTAL.labels(tier=tier).inc())` in
        # infrastructure/metrics.py. So a definition line
        # (`IDENTIFIER = Counter(/Gauge(/Histogram(`) never counts as a
        # writer, but any other line naming the identifier does, regardless
        # of which file it is in.
        definition = re.compile(r"^\s*\w+\s*=\s*(Counter|Gauge|Histogram)\(")
        src_root = REPO_ROOT / "src" / "reasoner"
        py_files = list(src_root.rglob("*.py"))

        dead = []
        for metric_name in sorted(referenced):
            identifier = identifier_for.get(metric_name)
            if not identifier:
                continue
            found_writer = False
            for f in py_files:
                for line in f.read_text(encoding="utf-8").splitlines():
                    if identifier in line and not definition.match(line):
                        found_writer = True
                        break
                if found_writer:
                    break
            if not found_writer:
                dead.append(metric_name)

        assert not dead, f"alerted on but never recorded: {dead}"

    def test_every_rule_has_severity_and_summary(self, rules):
        for rule in rules:
            assert rule.get("labels", {}).get("severity") in {"warning", "critical"}, rule["alert"]
            assert rule.get("annotations", {}).get("summary"), rule["alert"]


class TestPoolGaugeDirection:
    def test_free_gauge_uses_idle_size(self):
        """size - idle is BUSY connections; the alert reads this as 'free'."""
        src = (
            REPO_ROOT / "src" / "reasoner" / "application" / "services" / "health_service.py"
        ).read_text(encoding="utf-8")
        assert "REASONER_POSTGRES_POOL_FREE.set(_health_postgres_pool.get_idle_size())" in src
        assert "get_size() - _health_postgres_pool.get_idle_size()" not in src


class TestAlertmanagerSecretsAreNotCommittable:
    def test_secrets_dir_is_gitignored(self):
        """It will hold a Slack webhook URL and a PagerDuty routing key."""
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        assert "secrets/" in gitignore
