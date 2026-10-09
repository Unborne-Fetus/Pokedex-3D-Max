"""Launch the local Switch-only index and expose opt-in offline texture repair.

The repair endpoint is bound to 127.0.0.1 and requires an exact same-origin
POST. It runs the existing strict Switch shader rebuild; it never downloads a
replacement model source or starts the Windows EXE/installer.
"""
from __future__ import annotations

import functools
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import webbrowser

from sync_switch_web import ROOT, default_pack
from restore_switch_models import restore


REPAIR_LOG = ROOT / ".cache" / "switch-game-assets" / "index-texture-repair.log"
REPAIR_SCRIPT = ROOT / "scripts" / "setup_all.ps1"
REPAIR_STATUS_PATH = "/__pokedex3d/repair-status"
REPAIR_START_PATH = "/__pokedex3d/repair-textures"
repair_lock = threading.Lock()
repair_state = {"running": False, "finished": False, "exitCode": None, "error": ""}


def _read_log_tail() -> str:
    if not REPAIR_LOG.is_file():
        return ""
    try:
        with REPAIR_LOG.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            stream.seek(max(0, stream.tell() - 10000), os.SEEK_SET)
            return stream.read().decode("utf-8", errors="replace")[-8500:]
    except OSError:
        return ""


def _repair_available() -> bool:
    return os.name == "nt" and REPAIR_SCRIPT.is_file() and bool(shutil.which("powershell.exe"))


def _run_texture_repair() -> None:
    error = ""
    exit_code = 1
    try:
        REPAIR_LOG.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy",
            "Bypass", "-File", str(REPAIR_SCRIPT),
            "-SwitchAssetsOnly", "-SkipInstall", "-BakeSwitchMaterials",
        ]
        with REPAIR_LOG.open("wb") as log:
            log.write(b"Rebuilding original Switch shader textures for the browser index...\r\n")
            log.flush()
            result = subprocess.run(
                cmd,
                cwd=str(ROOT),
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
            exit_code = result.returncode
    except Exception as exc:
        error = str(exc)
    finally:
        with repair_lock:
            repair_state.update(
                running=False, finished=True, exitCode=exit_code, error=error
            )


class LocalIndexHandler(SimpleHTTPRequestHandler):
    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _is_local(self) -> bool:
        return self.client_address[0] in ("127.0.0.1", "::1")

    def do_GET(self) -> None:
        if urlsplit(self.path).path != REPAIR_STATUS_PATH:
            return super().do_GET()
        if not self._is_local():
            return self._json(403, {"error": "Localhost only"})
        with repair_lock:
            status = dict(repair_state)
        status["available"] = _repair_available()
        status["logTail"] = _read_log_tail() if status["running"] or status["finished"] else ""
        self._json(200, status)

    def do_POST(self) -> None:
        if urlsplit(self.path).path != REPAIR_START_PATH:
            return self._json(404, {"error": "Unknown endpoint"})
        expected_origin = f"http://127.0.0.1:{self.server.server_port}"
        if not self._is_local() or self.headers.get("Origin") != expected_origin:
            return self._json(403, {"error": "Same-origin local browser only"})
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._json(400, {"error": "Invalid request length"})
        if content_length > 1024 or content_length < 0:
            return self._json(413, {"error": "Request too large"})
        if content_length:
            self.rfile.read(content_length)
        if not _repair_available():
            return self._json(503, {
                "error": "Texture repair requires the complete project scripts and Windows PowerShell."
            })
        with repair_lock:
            if repair_state["running"]:
                return self._json(409, {"error": "A texture repair is already running"})
            repair_state.update(running=True, finished=False, exitCode=None, error="")
        threading.Thread(target=_run_texture_repair, daemon=True).start()
        self._json(202, {"running": True})


if __name__ == "__main__":
    if not restore(default_pack()):
        raise SystemExit(
            "No original Switch exports remain. Place and import original Switch archives first."
        )
    handler = functools.partial(LocalIndexHandler, directory=str(ROOT))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        url = f"http://127.0.0.1:{server.server_port}/index.html"
        print(
            f"Opening {url}\n"
            "Keep this window open while using the index or repairing textures.\n"
            "Texture repair can be started from the 'Repair textures' button in the viewer.",
            flush=True,
        )
        webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
