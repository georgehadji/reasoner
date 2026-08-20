"""
Neuro CLI
Manage the internal memory engine.
"""

import math

import click
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from reasoner.core.settings import settings
from reasoner.neuro.config import load_config

console = Console()


@click.group()
def main():
    """Neuro Memory Engine CLI."""
    pass


def _safe_num(value):
    """Return value if numeric and not NaN, else '?'."""
    if isinstance(value, (int, float)) and not math.isnan(value):
        return value
    return "?"


@main.command()
def status():
    """Check health and statistics."""
    cfg = load_config()
    url = f"http://{cfg.server.host}:{cfg.server.port}/api/neuro/health"
    # /health is gated by require_neuro_key like every other /api/neuro/*
    # route; without this header every call 403s once NEURO_INTERNAL_KEY is
    # set, which api/__init__.py requires in production.
    headers = {"X-Neuro-Key": settings.neuro_internal_key} if settings.neuro_internal_key else {}

    try:
        resp = httpx.get(url, timeout=5.0, headers=headers)
        if resp.status_code != 200:
            console.print(f"[red]Neuro Engine returned {resp.status_code}:[/red] {resp.text}")
            return
        data = resp.json()

        table = Table(title="Neuro Layer Status", show_header=False)
        table.add_row(
            "Status",
            f"[green]{data['status']}[/green]" if data["status"] == "ok" else "[red]Down[/red]",
        )
        table.add_row("Version", data.get("version", "?"))
        reasoning = data.get("reasoning", {})
        embedding = data.get("embedding", {})
        table.add_row(
            "Reasoning",
            f"{_safe_num(reasoning.get('active'))} (Healthy: {_safe_num(reasoning.get('healthy'))})",
        )
        table.add_row(
            "Embedding",
            f"{_safe_num(embedding.get('active'))} (Healthy: {_safe_num(embedding.get('healthy'))})",
        )

        sess = data.get("sessions", {})
        table.add_row(
            "Sessions",
            f"Hot: {_safe_num(sess.get('hot_sessions'))}, Warm: {_safe_num(sess.get('warm_sessions'))}, Cold: {_safe_num(sess.get('cold_sessions'))}",
        )

        console.print(Panel(table, title="Neuro Engine", border_style="cyan"))
    except Exception as e:
        console.print(f"[red]Error connecting to Neuro Engine:[/red] {e}")


@main.command()
@click.option("--host", default=None)
@click.option("--port", default=None, type=int)
def start(host, port):
    """Start the memory engine server."""
    import uvicorn
    from fastapi import FastAPI

    from reasoner.neuro.server import create_neuro_router

    cfg = load_config()
    h = host or cfg.server.host
    p = port or cfg.server.port

    # This builds a standalone app, bypassing api/__init__.py's startup
    # checks entirely -- including the one that refuses to boot in
    # production with no NEURO_INTERNAL_KEY set (/learn and /audit would
    # otherwise be an unauthenticated tenant-memory write and free LLM
    # proxy). Re-check it here so this entry point can't become that hole.
    if not settings.neuro_internal_key and settings.ENVIRONMENT == "production":
        console.print(
            "[red]NEURO_INTERNAL_KEY is unset in a production environment -- "
            "refusing to start an unauthenticated Neuro server.[/red]"
        )
        raise SystemExit(1)

    def app_factory():
        app = FastAPI(title="Neuro Memory Engine")
        app.include_router(create_neuro_router(cfg))
        return app

    console.print(f"[cyan]Starting Neuro Engine on {h}:{p}...[/cyan]")
    uvicorn.run(app_factory, host=h, port=p, factory=True)


if __name__ == "__main__":
    main()
