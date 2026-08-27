#!/usr/bin/env python
"""
Start all Reasoner servers.

By default starts:
  - Main API server      : http://localhost:8003
  - Neuro memory server  : http://localhost:50001

Usage:
  python start_all.py
  python start_all.py --no-neuro    # Skip standalone neuro server
  python start_all.py --check       # Run pre-flight checks first
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from reasoner.core.settings import settings

# ─────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
MAIN_SERVER_CMD = [sys.executable, "-m", "uvicorn", "asgi:app", "--host", settings.UVICORN_HOST, "--port", "8003"]
# Watch only the backend package: the repo root contains ui-next/node_modules,
# which makes a bare --reload watch thousands of irrelevant files.
MAIN_SERVER_RELOAD_ARGS = ["--reload", "--reload-dir", "src"]
NEURO_SERVER_CMD = [sys.executable, "-m", "reasoner.neuro.cli", "start"]
FRONTEND_DIR = REPO_ROOT / "ui-next"
FRONTEND_CMD = ["npm", "run", "dev"]


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def print_banner():
    print("=" * 64)
    print("  Reasoner - AI Reasoning Platform")
    print("  Server Orchestrator")
    print("=" * 64)
    print()


def run_preflight_checks() -> bool:
    """Run server_check.py and return True if all passed."""
    print("Running pre-flight checks...")
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "src" / "reasoner" / "server_check.py")],
        cwd=REPO_ROOT,
    )
    print()
    return result.returncode == 0


def _port_in_use(port: int) -> tuple[bool, int | None]:
    """Check if a TCP port is already bound. Returns (in_use, pid)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(("127.0.0.1", port))
            if result != 0:
                return False, None
    except Exception:
        return False, None

    # Port is in use — try to find the owning PID
    pid = None
    if sys.platform == "win32":
        try:
            output = subprocess.check_output(
                ["netstat", "-ano", "-p", "TCP"],
                text=True,
            )
            for line in output.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    if parts:
                        try:
                            pid = int(parts[-1])
                        except ValueError:
                            pass
                    break
        except Exception:
            pass
    else:
        try:
            output = subprocess.check_output(
                ["lsof", "-ti", f":{port}"],
                text=True,
            )
            pids = [int(p) for p in output.strip().split() if p.strip().isdigit()]
            if pids:
                pid = pids[0]
        except Exception:
            pass
    return True, pid


def _try_free_port(port: int, pid: int | None) -> bool:
    """Attempt to free a port. Returns True if freed."""
    # 1. Try npx kill-port first (handles Windows zombie sockets)
    npx_path = shutil.which("npx") or shutil.which("npx.cmd") or shutil.which("npx.ps1")
    if npx_path:
        cmd = [npx_path, "kill-port", str(port)]
        if sys.platform == "win32" and npx_path.endswith(".ps1"):
            cmd = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", npx_path, "kill-port", str(port)]
        elif sys.platform == "win32" and npx_path.endswith(".cmd"):
            # A .cmd shim needs an interpreter, but invoking it explicitly via
            # `cmd.exe /c` keeps every argument a separate argv entry. shell=True
            # would instead hand the whole line to the shell for re-parsing.
            cmd = ["cmd.exe", "/c", npx_path, "kill-port", str(port)]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                time.sleep(0.5)
                in_use, _ = _port_in_use(port)
                if not in_use:
                    return True
        except FileNotFoundError:
            pass

    # 2. Fallback: use psutil to find processes by port and kill them
    try:
        import psutil
        killed_any = False
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr.port == port and conn.pid:
                try:
                    p = psutil.Process(conn.pid)
                    p.terminate()
                    p.wait(timeout=3)
                    killed_any = True
                except psutil.NoSuchProcess:
                    pass
                except psutil.TimeoutExpired:
                    try:
                        p.kill()
                        killed_any = True
                    except Exception:
                        pass
        if killed_any:
            time.sleep(0.5)
            in_use, _ = _port_in_use(port)
            if not in_use:
                return True
    except ImportError:
        pass

    # 3. Fallback: kill by PID if we have one
    if pid is not None:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        else:
            subprocess.run(["kill", "-9", str(pid)], capture_output=True)
        time.sleep(0.5)
        in_use, _ = _port_in_use(port)
        return not in_use

    return False


def _wait_for_health(
    port: int,
    timeout: float = 30.0,
    proc: subprocess.Popen | None = None,
) -> bool:
    """Poll the backend root endpoint until it responds (any 2xx-4xx means it's up).

    Stops early if *proc* dies. A backend that exits on the first line -- a
    missing dependency, a bad import, a port it cannot bind -- is never going
    to answer, and spending the full timeout on it delays the error by half a
    minute and reports it as a timeout rather than as the crash it was.
    """
    import urllib.request
    url = f"http://127.0.0.1:{port}/"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if 200 <= resp.status < 500:
                    return True
        except urllib.error.HTTPError as exc:
            if 200 <= exc.code < 500:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def spawn_process(
    name: str,
    cmd: list[str] | str,
    env: dict | None = None,
    cwd: Path | None = None,
    shell: bool = False,
) -> subprocess.Popen:
    """Start a subprocess and return the handle."""
    print(f"[START] {name}")
    print(f"        {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
    process_env = {**os.environ, **(env or {})}
    work_dir = cwd or REPO_ROOT
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    if shell:
        kwargs["shell"] = True
    proc = subprocess.Popen(cmd, cwd=str(work_dir), env=process_env, **kwargs)
    return proc





def shutdown_process(name: str, proc: subprocess.Popen):
    """Gracefully terminate a subprocess and anything it spawned."""
    if proc.poll() is not None:
        return
    print(f"[STOP]  {name} (PID {proc.pid})")
    try:
        if sys.platform == "win32":
            if getattr(proc, "_reasoner_shell", False):
                # The handle we hold is cmd.exe, not the server. Terminating
                # it leaves `next dev` running and port 3000 bound, which is
                # the state the next start then aborts on. taskkill /T is the
                # only way to reach the whole tree from here.
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                    capture_output=True,
                )
            else:
                proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
        proc.wait()


def _import_smoke_test() -> bool:
    """Quick import check to verify the backend package loads cleanly."""
    try:
        import reasoner.api  # noqa: F401
        return True
    except Exception as exc:
        print(f"[ERROR] Import smoke test failed: {exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Start all Reasoner servers")
    parser.add_argument("--no-neuro", action="store_true", help="Skip the standalone neuro server")
    parser.add_argument("--no-frontend", action="store_true", help="Skip the Next.js frontend dev server")
    parser.add_argument("--check", action="store_true", help="Run pre-flight checks before starting")
    parser.add_argument("--main-port", type=int, default=8003, help="Port for the main API server")
    parser.add_argument("--neuro-port", type=int, default=50001, help="Port for the standalone neuro server")
    parser.add_argument("--frontend-port", type=int, default=3000, help="Port for the Next.js frontend dev server")
    parser.add_argument("--force", action="store_true", help="Auto-kill existing processes / free zombie sockets on conflicting ports")
    parser.add_argument("--no-reload", action="store_true", help="Disable backend autoreload (the frontend dev server always hot-reloads)")
    args = parser.parse_args()

    print_banner()

    if args.check:
        if not run_preflight_checks():
            print("Pre-flight checks failed. Aborting.")
            return 1

    # ── Import smoke test ────────────────────────────────────────
    if not _import_smoke_test():
        print("\n[ABORT] Backend failed to import. Common fixes:")
        print("        1. Ensure all dependencies are installed: pip install -r requirements.txt")
        print("        2. Check for syntax errors in recently edited files")
        print("        3. Verify PYTHONPATH includes the 'src' directory")
        return 1

    # ── Port conflict check ──────────────────────────────────────
    # Two things this list fixes. Only services this run will actually start
    # are checked -- the old loop checked all three unconditionally, so
    # --no-frontend still aborted the run when something unrelated held
    # :3000. And each entry carries its own flag, so the "use a different
    # port" hint names the one that would move the service in front of the
    # reader rather than always naming --main-port.
    port_checks = [("Main API Server", args.main_port, "--main-port")]
    if not args.no_neuro:
        port_checks.append(("Neuro Server", args.neuro_port, "--neuro-port"))
    if not args.no_frontend:
        port_checks.append(("Next.js Frontend", args.frontend_port, "--frontend-port"))

    for svc, port, flag in port_checks:
        in_use, pid = _port_in_use(port)
        if not in_use:
            continue

        owner = f"PID {pid}" if pid else "zombie socket"
        if args.force:
            print(f"\n[INFO]  {svc} port {port} is in use ({owner}). Freeing...")
            if _try_free_port(port, pid):
                print(f"[OK]    Port {port} freed.")
                continue
            print(f"[WARN]  Could not free port {port}.")

        print(f"\n[ABORT] {svc} port {port} is already in use ({owner}).")
        print("        Stop the existing process or use a different port:")
        print(f"        python start_all.py {flag} {port + 1}")
        if not args.force:
            print("        Or force-free the port:")
            print("        python start_all.py --force")
        return 1

    processes: list[tuple[str, subprocess.Popen]] = []

    try:

        # Start Next.js frontend dev server first (it takes longest to boot)
        if not args.no_frontend:
            if not (FRONTEND_DIR / "package.json").exists():
                print(f"[WARN] Frontend directory not found at {FRONTEND_DIR}, skipping.")
            elif shutil.which("npm") is None:
                print("[WARN] npm not found in PATH, skipping frontend start.")
            else:
                if not os.environ.get("CSRF_SECRET"):
                    # Next loads ui-next/.env*, not the repo-root .env — but
                    # reasoner.core.settings has already read the root .env
                    # into os.environ by the time this runs, so an unset value
                    # here means it is genuinely unset. Without it the proxy
                    # middleware raises on every request and the whole site
                    # answers 500, with the reason visible only in the dev
                    # server's own console.
                    print("[WARN] CSRF_SECRET is not set. The frontend will return 500 on")
                    print("       every route until it is. Set it in .env (32+ random bytes).")
                # API_BASE_URL is the variable the Next proxy routes read
                # (getApiBaseUrl in ui-next/src/lib/security-server.ts); it
                # falls back to a hardcoded :8003 when unset, so without this
                # line --main-port moves the backend and leaves every proxy
                # route pointing at the old port.
                frontend_env = {
                    **os.environ,
                    "PORT": str(args.frontend_port),
                    "API_BASE_URL": f"http://localhost:{args.main_port}",
                }
                frontend_shell = sys.platform == "win32"
                frontend_cmd = " ".join(FRONTEND_CMD) if frontend_shell else FRONTEND_CMD.copy()
                frontend_proc = spawn_process(
                    "Next.js Frontend",
                    frontend_cmd,
                    env=frontend_env,
                    cwd=FRONTEND_DIR,
                    shell=frontend_shell,
                )
                if frontend_shell:
                    frontend_proc._reasoner_shell = True  # type: ignore[attr-defined]
                processes.append(("Next.js Frontend", frontend_proc))
                # No sleep here: next dev boots on its own clock and nothing
                # below waits on it. The backend health poll further down is
                # the only readiness gate that buys anything, and it starts
                # sooner for the three seconds this used to cost.

        # Start main API server
        main_cmd = MAIN_SERVER_CMD.copy()
        if "--port" in main_cmd:
            main_cmd[main_cmd.index("--port") + 1] = str(args.main_port)
        if not args.no_reload:
            main_cmd.extend(MAIN_SERVER_RELOAD_ARGS)
            print("[INFO]  Backend autoreload enabled (watching src/). Use --no-reload to disable.")
        main_proc = spawn_process("Main API Server", main_cmd)
        processes.append(("Main API Server", main_proc))

        # ── Health polling ───────────────────────────────────────────
        print("[WAIT]  Polling backend health...")
        if _wait_for_health(args.main_port, timeout=30.0, proc=main_proc):
            print(f"[OK]    Backend responding on port {args.main_port}")
        elif main_proc.poll() is not None:
            # Printing "started successfully" over a process that has already
            # exited is worse than printing nothing: it sends the reader
            # looking for a network problem instead of at the traceback the
            # backend just wrote above this line.
            print(f"[ABORT] Backend exited with code {main_proc.returncode} before serving.")
            print("        The cause is in the backend output above.")
            raise SystemExit(main_proc.returncode or 1)
        else:
            print("[WARN]  Backend did not respond within 30s. It may still be starting.")

        # Start standalone neuro server if requested
        if not args.no_neuro:
            neuro_cmd = NEURO_SERVER_CMD.copy()
            neuro_cmd.extend(["--port", str(args.neuro_port)])
            neuro_env = {
                **os.environ,
                "PYTHONPATH": str(REPO_ROOT / "src"),
            }
            neuro_proc = spawn_process("Neuro Server", neuro_cmd, env=neuro_env)
            processes.append(("Neuro Server", neuro_proc))
            time.sleep(1)

        print()
        print("-" * 64)
        print("  Servers started successfully!")
        print()
        print(f"  Main API:     http://localhost:{args.main_port}")
        print(f"  API Docs:     http://localhost:{args.main_port}/docs")
        print(f"  WebSocket:    ws://localhost:{args.main_port}/ws")
        if not args.no_frontend:
            print(f"  Frontend:     http://localhost:{args.frontend_port}")
        if not args.no_neuro:
            print(f"  Neuro API:    http://localhost:{args.neuro_port}/neuro/health")
        print()
        print("  Press Ctrl+C to stop all servers")
        print("-" * 64)
        print()

        # Wait for all processes
        while True:
            for name, proc in processes:
                ret = proc.poll()
                if ret is not None:
                    print(f"[EXIT] {name} exited with code {ret}")
                    raise SystemExit(ret or 0)
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n[INTERRUPT] Shutting down servers...")
    finally:
        for name, proc in processes:
            shutdown_process(name, proc)
        print("[DONE] All servers stopped.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
