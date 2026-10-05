#!/usr/bin/env python3
"""Serve the static archive on a local HTTP server."""

from __future__ import annotations

import argparse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    handler = lambda *values, **kwargs: SimpleHTTPRequestHandler(*values, directory=str(ROOT), **kwargs)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving on http://{args.host}:{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
