#!/usr/bin/env python3
"""Espera uma URL responder (qualquer status < 500). Uso: wait_for_url.py URL [segundos]"""

from __future__ import annotations

import ssl
import sys
import time
import urllib.error
import urllib.request


def main() -> int:
    url = sys.argv[1]
    timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 120
    deadline = time.time() + timeout
    ctx = ssl.create_default_context()
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5, context=ctx) as resp:  # noqa: S310
                if resp.status < 500:
                    print(f"[testkit] {url} respondeu {resp.status}")
                    return 0
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                print(f"[testkit] {url} respondeu {exc.code}")
                return 0
            last_error = f"HTTP {exc.code}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(2)
    print(f"[testkit] {url} não respondeu em {timeout:.0f}s ({last_error})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
