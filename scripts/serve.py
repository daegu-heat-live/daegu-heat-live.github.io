"""로컬 미리보기 서버: web/ 을 캐시 없이 제공한다.  python scripts/serve.py [port]"""
import functools
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"


class NoCache(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".geojson": "application/geo+json"}

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"http://localhost:{port}/  ({WEB})")
    ThreadingHTTPServer(("127.0.0.1", port), functools.partial(NoCache, directory=str(WEB))).serve_forever()
