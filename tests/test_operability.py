"""Operational readiness: monitoring signals that actually fire.

Each of these was either absent or silently broken:
  - Alertmanager could not parse its config, so no alert could ever be delivered.
  - No rule referenced the scrape target's own health, so a dead backend was silent.
  - The Postgres "free connections" gauge was fed from the health probe's own
    1-2 connection pool, so the pool alerts read a number unrelated to load.
    The gauges and both alerts were removed.
  - reasoner_quota_exceeded_total was defined and alerted on but never
    incremented, so the abuse tripwire could never fire.
"""

from __future__ import annotations

import ast
import functools
import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[1]
MONITORING = REPO_ROOT / "docs" / "monitoring"


SRC_ROOT = REPO_ROOT / "src" / "reasoner"
METRICS_MODULE = SRC_ROOT / "infrastructure" / "metrics.py"
METRICS_PORT = SRC_ROOT / "core" / "ports" / "metrics_port.py"
METRIC_FACTORIES = {"Counter", "Gauge", "Histogram", "Summary"}
WRITE_METHODS = {"inc", "dec", "set", "observe", "set_to_current_time", "time"}


@functools.cache
def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _defined_metrics() -> dict[str, str]:
    """Exposed Prometheus series name -> Python identifier, from `X = Counter("name", ...)`."""
    out: dict[str, str] = {}
    for node in ast.walk(_parse(METRICS_MODULE)):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        call = node.value
        factory = call.func.id if isinstance(call.func, ast.Name) else None
        if factory not in METRIC_FACTORIES or not call.args:
            continue
        first = call.args[0]
        target = node.targets[0]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            continue
        if not isinstance(target, ast.Name):
            continue
        name = first.value
        out[name] = target.id
        if factory == "Counter" and not name.endswith("_total"):
            out[name + "_total"] = target.id
        if factory == "Histogram":
            for suffix in ("_bucket", "_sum", "_count"):
                out[name + suffix] = target.id
    return out


def _alerted_identifiers(rules) -> dict[str, str]:
    """Series name -> identifier, for every defined metric an alert expr mentions."""
    defined = _defined_metrics()
    tokens = set(re.findall(r"[a-zA-Z_:][a-zA-Z0-9_:]*", " ".join(r["expr"] for r in rules)))
    return {tok: defined[tok] for tok in tokens if tok in defined}


def _write_target(call: ast.Call) -> str | None:
    """Identifier written by `IDENT[.labels(...)].inc()` style calls, else None."""
    func = call.func
    if not (isinstance(func, ast.Attribute) and func.attr in WRITE_METHODS):
        return None
    node = func.value
    while isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr != "labels":
            return None
        node = node.func.value
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):  # e.g. metrics_mod.IDENT.inc()
        return node.attr
    return None


def _py_files():
    return [p for p in SRC_ROOT.rglob("*.py") if p != METRICS_MODULE]


def _direct_writers() -> set[str]:
    """Identifiers with a real write call in any module other than the definition one."""
    written: set[str] = set()
    for path in _py_files():
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.Call):
                target = _write_target(node)
                if target:
                    written.add(target)
    return written


def _hook_driven_identifiers() -> set[str]:
    """Identifiers written only through a core metrics-port hook that something calls.

    application/ may not import infrastructure, so some counters are written by
    a lambda that infrastructure/metrics.py registers with a core setter
    (`set_quota_exceeded_counter(lambda t: IDENT.labels(tier=t).inc())`), and
    the application calls the matching emitter (`count_quota_exceeded(...)`).
    Registering the lambda is wiring, not a write: the identifier only counts
    when the emitter is actually called from code outside metrics_port.py and
    the definition module, so deleting that call makes the alert silent here too.
    """
    emitters_called: set[str] = set()
    for path in _py_files():
        if path == METRICS_PORT:
            continue
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
                if name and name.startswith("count_"):
                    emitters_called.add(name)

    hooked: set[str] = set()
    for node in ast.walk(_parse(METRICS_MODULE)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        setter = node.func.id
        m = re.fullmatch(r"set_(\w+?)_counter", setter)
        if not m or f"count_{m.group(1)}" not in emitters_called:
            continue
        for arg in node.args:
            for inner in ast.walk(arg):
                if isinstance(inner, ast.Call):
                    target = _write_target(inner)
                    if target:
                        hooked.add(target)
    return hooked


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
        tripwire (QuotaExceededSpike), and incremented nowhere. This maps every
        metric named in an alert `expr:` to its Python identifier and requires
        a real write call (`.inc()`/`.set()`/`.observe()`...) outside the
        definition module, so "defined but never incremented" fails CI rather
        than shipping as a silent alert.

        Purely static (ast): it does not import prometheus_client, whose
        private `_name` is absent when the library is not installed (CI), which
        used to turn this check into a no-op there.
        """
        alerted = _alerted_identifiers(rules)
        assert alerted, "no alerted metric resolved to a definition: parser is broken"
        direct = _direct_writers()
        hooked = _hook_driven_identifiers()

        dead = sorted(
            name for name, ident in alerted.items()
            if ident not in direct and ident not in hooked
        )
        assert not dead, f"alerted on but never recorded: {dead}"

    def test_pool_gauges_are_not_alerted_on(self, rules):
        """They were fed from the health probe's private pool, not a serving pool."""
        exprs = " ".join(r["expr"] for r in rules)
        assert "reasoner_postgres_pool" not in exprs

    def test_every_rule_has_severity_and_summary(self, rules):
        for rule in rules:
            assert rule.get("labels", {}).get("severity") in {"warning", "critical"}, rule["alert"]
            assert rule.get("annotations", {}).get("summary"), rule["alert"]


class TestAlertmanagerSecretsAreNotCommittable:
    def test_secrets_dir_is_gitignored(self):
        """It will hold a Slack webhook URL and a PagerDuty routing key."""
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        assert "secrets/" in gitignore
