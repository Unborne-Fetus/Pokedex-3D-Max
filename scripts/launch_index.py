"""Sync downloaded Switch models and open the index over local HTTP."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import webbrowser
from sync_switch_web import ROOT, default_pack, sync_pack

if __name__ == "__main__":
    sync_pack(default_pack())
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(ROOT))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        url = f"http://127.0.0.1:{server.server_port}/index.html"
        print(f"Opening {url}\nKeep this window open while using the index. Ctrl+C stops it.", flush=True)
        webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
