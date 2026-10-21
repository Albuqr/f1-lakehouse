#!/usr/bin/env python3
"""Gera um código TOTP (RFC 6238) a partir de um segredo base32.

Uso: totp.py SEGREDO [--digits 6] [--period 30] [--min-remaining 20]

--min-remaining espera a próxima janela se restarem menos segundos que o valor,
evitando que o código expire no meio de um fluxo automatizado (ex.: Maestro).
Aceita também URIs otpauth://totp/...?secret=XXX.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import struct
import sys
import time
from urllib.parse import parse_qs, urlparse


def normalize_secret(raw: str) -> str:
    if raw.startswith("otpauth://"):
        query = parse_qs(urlparse(raw).query)
        raw = query.get("secret", [""])[0]
    secret = raw.replace(" ", "").replace("-", "").upper()
    return secret + "=" * (-len(secret) % 8)


def totp(secret: str, digits: int = 6, period: int = 30, at: float | None = None, algorithm: str = "sha1") -> str:
    key = base64.b32decode(normalize_secret(secret), casefold=True)
    counter = int((at if at is not None else time.time()) // period)
    digest = hmac.new(key, struct.pack(">Q", counter), getattr(hashlib, algorithm)).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(code).zfill(digits)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("secret")
    parser.add_argument("--digits", type=int, default=6)
    parser.add_argument("--period", type=int, default=30)
    parser.add_argument("--algorithm", default="sha1", choices=["sha1", "sha256", "sha512"])
    parser.add_argument("--min-remaining", type=int, default=0)
    args = parser.parse_args()
    remaining = args.period - (time.time() % args.period)
    if remaining < args.min_remaining:
        time.sleep(remaining + 0.5)
    print(totp(args.secret, args.digits, args.period, algorithm=args.algorithm))
    return 0


if __name__ == "__main__":
    sys.exit(main())
