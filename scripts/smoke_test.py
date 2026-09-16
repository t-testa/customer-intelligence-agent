"""Smoke-test deterministic endpoints; standard library only and no live model calls."""

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


def smoke(base_url: str, token: str = "", attempts: int = 1):
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("An HTTP(S) base URL is required")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("Remote smoke tests require HTTPS")
    for path in ("/health", "/metrics", "/customers/3/risk"):
        for attempt in range(attempts):
            request = urllib.request.Request(base_url.rstrip("/") + path)
            if token:
                request.add_header("Authorization", f"Bearer {token}")
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    body = json.load(response)
                    assert response.status == 200 and response.headers.get("X-Request-ID")
                if path == "/health":
                    assert body["database"] == "connected"
                elif path == "/metrics":
                    assert "requests_total" in body
                else:
                    assert body["customer_id"] == 3 and 0 <= body["risk_score"] <= 8
                print(f"PASS {path}")
                break
            except (urllib.error.URLError, TimeoutError, AssertionError, ValueError, KeyError):
                if attempt + 1 == attempts:
                    raise RuntimeError(f"Smoke test failed: {path}") from None
                time.sleep(3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--attempts", type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.attempts <= 30:
        parser.error("attempts must be 1–30")
    smoke(args.base_url, os.environ.get("READER_API_KEY", ""), args.attempts)


if __name__ == "__main__":
    main()
