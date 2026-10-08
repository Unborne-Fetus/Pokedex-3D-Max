"""Sync downloaded Switch models and open the index over local HTTP."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import webbrowser
from sync_switch_web import ROOT, default_pack
from restore_switch_models import restore

if __name__ == "__main__":
    if not restore(default_pack()):
        raise SystemExit("No original Switch exports remain. Run setup-all.bat switch to convert the downloaded archives.")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(ROOT))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        url = f"http://127.0.0.1:{server.server_port}/index.html"
        print(f"Opening {url}\nKeep this window open while using the index. Ctrl+C stops it.", flush=True)
        webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
