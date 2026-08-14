"""Operational readiness: alerting that fires, backups that exist, a way back.

Each of these was either absent or silently broken:
  - Alertmanager could not parse its config, so no alert could ever be delivered.
  - No rule referenced the scrape target's health, so a dead backend was silent.
  - The Postgres "free connections" gauge was inverted, so the critical
    pool-exhaustion alert fired on an idle pool and stayed quiet on a full one.
  - Backups and rollback existed only as prose.
"""

from __future__ import annotations

import os
import stat
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

    def test_liveness_rule_targets_a_real_scrape_job(self, rules, prometheus_jobs):
        """A rule naming a job that isn't scraped can never fire."""
        import re

        for rule in rules:
            for job in re.findall(r'job="([^"]+)"', rule["expr"]):
                assert job in prometheus_jobs, (
                    f"{rule['alert']} references job {job!r}, "
                    f"but prometheus.yml scrapes {sorted(prometheus_jobs)}"
                )

    def test_cost_is_alerted(self, rules):
        """Cost was measured but never alerted on."""
        exprs = " ".join(r["expr"] for r in rules)
        assert "reasoner_llm_call_cost_usd_total" in exprs, (
            "no alert watches LLM spend — a runaway is invisible until the bill"
        )

    def test_every_rule_has_severity_and_summary(self, rules):
        for rule in rules:
            assert rule.get("labels", {}).get("severity") in {"warning", "critical"}, rule["alert"]
            assert rule.get("annotations", {}).get("summary"), rule["alert"]


class TestPoolGaugeDirection:
    def test_free_gauge_uses_idle_size(self):
        """size - idle is BUSY connections; the alert reads this as 'free'."""
        src = (REPO_ROOT / "src" / "reasoner" / "api" / "routes" / "health.py").read_text(
            encoding="utf-8"
        )
        assert "REASONER_POSTGRES_POOL_FREE.set(_health_postgres_pool.get_idle_size())" in src
        assert "POOL_FREE.set(\n" not in src.replace(" ", "")


class TestOperationalScripts:
    @pytest.mark.parametrize(
        "script", ["backup_db.sh", "restore_db.sh", "deploy.sh", "rollback.sh", "verify_ci.sh"]
    )
    def test_script_exists_and_is_executable(self, script):
        path = REPO_ROOT / "scripts" / script
        assert path.exists(), f"{script} is missing"
        assert os.stat(path).st_mode & stat.S_IXUSR, f"{script} is not executable"

    @pytest.mark.parametrize(
        "script", ["backup_db.sh", "restore_db.sh", "deploy.sh", "rollback.sh"]
    )
    def test_script_fails_fast(self, script):
        """An ops script that continues past an error can do real damage."""
        body = (REPO_ROOT / "scripts" / script).read_text(encoding="utf-8")
        assert "set -euo pipefail" in body, f"{script} does not fail fast"

    def test_restore_offers_a_nondestructive_drill(self):
        """An untested backup is not a backup."""
        body = (REPO_ROOT / "scripts" / "restore_db.sh").read_text(encoding="utf-8")
        assert "--drill" in body

    def test_destructive_restore_requires_confirmation(self):
        body = (REPO_ROOT / "scripts" / "restore_db.sh").read_text(encoding="utf-8")
        assert "--force" in body and "read -r CONFIRM" in body

    def test_deploy_builds_before_restarting(self):
        """`down` before `build` leaves production down on a build failure."""
        raw = (REPO_ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
        # Comments explain why `down` is wrong, so only inspect real commands.
        commands = "\n".join(
            line for line in raw.splitlines() if not line.strip().startswith("#")
        )
        assert "docker compose build" in commands
        assert "docker compose down" not in commands, (
            "deploy must never tear the running stack down before its replacement builds"
        )
        assert commands.index("docker compose build") < commands.index("docker compose up -d")


class TestStagingTier:
    def test_staging_overlay_exists(self):
        assert (REPO_ROOT / "docker-compose.staging.yml").exists()

    def test_staging_does_not_collide_with_production_ports(self):
        staging = _load(REPO_ROOT / "docker-compose.staging.yml")
        prod = _load(REPO_ROOT / "docker-compose.yml")
        staging_ports = set(staging["services"]["caddy"]["ports"])
        prod_ports = set(prod["services"]["caddy"]["ports"])
        assert not (staging_ports & prod_ports), "staging would fight production for ports"

    def test_staging_caps_spend(self):
        """A looping test on staging must not be able to run up a real bill."""
        staging = _load(REPO_ROOT / "docker-compose.staging.yml")
        env = staging["services"]["backend"]["environment"]
        joined = " ".join(env)
        assert "SPEND_CAP_PER_RUN_USD" in joined
        assert "SPEND_CAP_MONTHLY_USD" in joined


class TestAlertmanagerSecretsAreNotCommittable:
    def test_secrets_dir_is_gitignored(self):
        """It will hold a Slack webhook URL and a PagerDuty routing key."""
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        assert "secrets/" in gitignore


class TestSseErrorsDoNotLeakInternals:
    def test_stream_error_is_gated_on_environment(self):
        src = (REPO_ROOT / "src" / "reasoner" / "api" / "streaming.py").read_text(
            encoding="utf-8"
        )
        assert 'settings.ENVIRONMENT != "production"' in src, (
            "the SSE generator bypasses FastAPI's exception handlers, so it must "
            "gate exception text on the environment itself"
        )
        assert "traceback.print_exc()" not in src, (
            "print_exc writes outside the logger, skipping secret redaction"
        )
        assert "correlation_id" in src
