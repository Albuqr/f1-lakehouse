#!/usr/bin/env python3
"""Imprime o cabeçalho de autenticação de um papel para ferramentas de linha de comando.

Uso: api_token.py PAPEL  ->  "Authorization: Bearer xxx" (ou vazio se não houver token)
Usa <PREFIXO>_TOKEN quando definido; senão, faz o login por API (auth.api) com usuário/senha.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config as cfgmod  # noqa: E402
from totp import totp  # noqa: E402


def render(value, env):
    if isinstance(value, str):
        for key, val in env.items():
            value = value.replace("{{" + key + "}}", val)
        return value
    if isinstance(value, dict):
        return {k: render(v, env) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, env) for v in value]
    return value


def post(url: str, body: dict, content_type: str) -> dict:
    if content_type == "form":
        data, ctype = urllib.parse.urlencode(body).encode(), "application/x-www-form-urlencoded"
    else:
        data, ctype = json.dumps(body).encode(), "application/json"
    req = urllib.request.Request(url, data=data, headers={"Content-Type": ctype}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        return json.loads(resp.read().decode() or "{}")


def main() -> int:
    cfg = cfgmod.load()
    role = next((r for r in cfg["auth"]["roles"] if r["name"] == sys.argv[1]), None)
    if not role:
        print(f"papel desconhecido: {sys.argv[1]}", file=sys.stderr)
        return 1
    prefix = role["envPrefix"]
    get = lambda s: os.environ.get(f"{prefix}_{s}", "")  # noqa: E731
    strategy = role.get("strategy") or cfg["auth"]["strategy"]
    bearer = cfg["auth"]["bearer"]
    if get("TOKEN"):
        print(f"{bearer['headerName']}: {bearer['headerPrefix']}{get('TOKEN')}")
        return 0
    api = cfg["auth"]["api"]
    if strategy != "api" or not api.get("tokenJsonPath"):
        return 0
    base = (cfg["api"].get("baseUrl") or cfg["web"]["baseUrl"]).rstrip("/")
    env = {"username": get("USERNAME"), "password": get("PASSWORD"), "email": get("EMAIL") or get("USERNAME")}
    data = post(base + api["path"], render(api["body"], env), api.get("contentType", "json"))
    if api.get("mfa"):
        env["totp"] = totp(get("TOTP_SECRET")) if get("TOTP_SECRET") else ""
        data = post(base + api["mfa"]["path"], render(api["mfa"]["body"], env), api.get("contentType", "json"))
    token = data
    for part in api["tokenJsonPath"].split("."):
        token = token.get(part) if isinstance(token, dict) else None
    if not token:
        print(f"token não encontrado em {api['tokenJsonPath']}", file=sys.stderr)
        return 1
    print(f"{api['headerName']}: {api['headerPrefix']}{token}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"[testkit] login por API falhou: {exc}", file=sys.stderr)
        sys.exit(1)
