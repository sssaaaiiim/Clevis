"""Serve only the local static demo site: python scripts/serve_testsite.py."""

import argparse
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SITE_ROOT = Path(__file__).resolve().parents[1] / "testsite"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        # Test-site requests may include private query strings; do not log them.
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("TESTSITE_PORT", "8765"))
    )
    args = parser.parse_args()
    handler = partial(QuietHandler, directory=str(SITE_ROOT))
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"Demo test site: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
