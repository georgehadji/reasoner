#!/usr/bin/env python
"""
Kill all Reasoner-related servers.

Usage:
  python kill_servers.py
  python kill_servers.py --force   # Skip graceful termination, kill immediately
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.resolve()

TARGET_KEYWORDS = [
    "uvicorn",
    "reasoner.neuro.cli",
    "start_all.py",
    "api.py",
]

# Also kill frontend node processes that are inside our repo
FRONTEND_DIR_NAME = "ui-next"

# Known ports to force-free (handles Windows zombie sockets)
TARGET_PORTS = [8003, 8002, 3000, 50001]


def _kill_processes(force: bool = False) -> int:
    """Find and terminate/kill Reasoner-related processes. Returns count."""
    try:
        import psutil
    except ImportError:
        print("[WARN] psutil not installed. Falling back to taskkill / pkill.")
        return _kill_processes_fallback(force)

    killed = 0
    for proc in psutil.process_iter(["pid", "name", "cmdline", "cwd"]):
        try:
            info = proc.info
            cmdline = info.get("cmdline") or []
            cmd_str = " ".join(cmdline).lower()
            name = (info.get("name") or "").lower()
            cwd = info.get("cwd")
            pid = info["pid"]

            # Avoid killing ourselves
            if pid == os.getpid():
                continue

            is_target = False
            # Match by command-line keyword
            for kw in TARGET_KEYWORDS:
                if kw.lower() in cmd_str:
                    is_target = True
                    break

            # Match frontend node/npm running inside ui-next
            if not is_target and (name in ("node.exe", "node") or "npm" in name):
                if cwd and FRONTEND_DIR_NAME in Path(cwd).as_posix():
                    is_target = True

            # Extra safety: if cwd is inside REPO_ROOT, be more aggressive with matches
            in_repo = bool(cwd and Path(cwd).resolve() == REPO_ROOT)
            if in_repo and ("python" in name and "reasoner" in cmd_str):
                is_target = True

            if not is_target:
                continue

            label = " ".join(cmdline[:3]) if cmdline else name
            print(f"[KILL] {label} (PID {pid})")
            if force:
                proc.kill()
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except psutil.TimeoutExpired:
                    print(f"[FORCE] {label} (PID {pid}) did not terminate in 5s — killing.")
                    proc.kill()
                    proc.wait(timeout=5)
            killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception as exc:
            print(f"[WARN] Error handling PID {info.get('pid', '?')}: {exc}")

    return killed


def _kill_processes_fallback(force: bool = False) -> int:
    """Fallback when psutil is missing."""
    killed = 0
    if sys.platform == "win32":
        for kw in TARGET_KEYWORDS:
            result = subprocess.run(
                ["taskkill", "/F" if force else "/T", "/IM", kw],
                capture_output=True,
            )
            if result.returncode == 0:
                killed += 1
        # Node fallback
        subprocess.run(["taskkill", "/F" if force else "/T", "/IM", "node.exe"], capture_output=True)
    else:
        for kw in TARGET_KEYWORDS:
            result = subprocess.run(["pkill", "-9" if force else "-15", "-f", kw], capture_output=True)
            if result.returncode == 0:
                killed += 1
        subprocess.run(["pkill", "-9" if force else "-15", "-f", "node"], capture_output=True)
    return killed


def _kill_ports() -> int:
    """Force-free known ports (handles Windows zombie sockets)."""
    freed = 0
    for port in TARGET_PORTS:
        try:
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                if s.connect_ex(("127.0.0.1", port)) != 0:
                    continue  # Port already free
        except Exception:
            continue

        print(f"[PORT] Port {port} is occupied — attempting to free...")

        # 1. Try npx kill-port first (handles zombie sockets on Windows)
        npx_path = shutil.which("npx") or shutil.which("npx.cmd") or shutil.which("npx.ps1")
        if npx_path:
            cmd = [npx_path, "kill-port", str(port)]
            if sys.platform == "win32" and npx_path.endswith(".ps1"):
                cmd = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", npx_path, "kill-port", str(port)]
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    shell=sys.platform == "win32" and npx_path.endswith(".cmd"),
                )
                if result.returncode == 0:
                    # Verify the port is actually free (zombie sockets may survive)
                    time.sleep(0.3)
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.settimeout(1)
                            if s.connect_ex(("127.0.0.1", port)) != 0:
                                print(f"[OK]   Freed port {port}")
                                freed += 1
                                continue
                    except Exception:
                        pass
                    print(f"[WARN] kill-port reported success but port {port} is still occupied")
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
                        print(f"[OK]   Terminated PID {conn.pid} on port {port}")
                        killed_any = True
                    except psutil.NoSuchProcess:
                        pass
                    except psutil.TimeoutExpired:
                        try:
                            p.kill()
                            print(f"[OK]   Killed PID {conn.pid} on port {port}")
                            killed_any = True
                        except Exception:
                            pass
            if killed_any:
                freed += 1
                continue
        except ImportError:
            pass

        # 3. Last resort: Windows taskkill by PID from netstat
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
                                subprocess.run(
                                    ["taskkill", "/F", "/PID", str(pid)],
                                    capture_output=True,
                                )
                                print(f"[OK]   Killed PID {pid} on port {port}")
                                freed += 1
                            except ValueError:
                                pass
                        break
            except Exception:
                pass
    return freed


def _port_owner(port: int) -> str:
    """Describe what holds *port*, without needing psutil or PowerShell."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        if sock.connect_ex(("127.0.0.1", port)) != 0:
            return "free"

    try:
        import psutil
    except ImportError:
        return "in use"

    for conn in psutil.net_connections(kind="inet"):
        if conn.laddr and conn.laddr.port == port and conn.pid:
            try:
                return f"{psutil.Process(conn.pid).name()} (PID {conn.pid})"
            except psutil.Error:
                return f"PID {conn.pid}"
    return "in use"


def print_status() -> None:
    """Print the occupancy of every port this script would free."""
    print("  Active Reasoner processes:")
    for port in TARGET_PORTS:
        print(f"    :{port}  ->  {_port_owner(port)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Kill all Reasoner servers")
    parser.add_argument("--force", action="store_true", help="Kill immediately without graceful termination")
    parser.add_argument(
        "--status",
        action="store_true",
        help="Report what holds each Reasoner port and exit without killing anything",
    )
    args = parser.parse_args()

    if args.status:
        print_status()
        return 0

    print("=" * 64)
    print("  Reasoner - Server Killer")
    print("=" * 64)
    print()

    killed = _kill_processes(force=args.force)
    if killed:
        print(f"[OK]   Terminated {killed} process(es).")
    else:
        print("[INFO] No matching Reasoner processes found.")

    freed = _kill_ports()
    if freed:
        print(f"[OK]   Freed {freed} port(s).")

    print()
    print("[DONE] All done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
