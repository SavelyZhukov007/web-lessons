from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


if __name__ == "__main__":
    handler = partial(SimpleHTTPRequestHandler, directory=str(Path(__file__).parent))
    with ThreadingHTTPServer(("127.0.0.1", 8000), handler) as server:
        print("Сайт: http://127.0.0.1:8000 (Ctrl+C — остановить)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
