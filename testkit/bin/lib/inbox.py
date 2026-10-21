#!/usr/bin/env python3
"""Busca o link mágico ou código mais recente enviado por e-mail a um destinatário.

Uso: inbox.py link|code DESTINATARIO --since EPOCH_SEGUNDOS

Tipos suportados (auth.inbox.type em testkit.config.json):
  mailpit  -> API do Mailpit (http://host:8025)
  mailhog  -> API v2 do MailHog
  http     -> URL própria que devolve o texto/HTML do último e-mail;
              use {{email}} na URL (ex.: https://api.exemplo/test-inbox?to={{email}})
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config as cfgmod  # noqa: E402


def fetch(url: str, headers: dict[str, str]) -> str:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - URL vem da config do projeto
        return resp.read().decode("utf-8", errors="replace")


def parse_time(value: str) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def latest_body(inbox: dict, recipient: str, since: float) -> str | None:
    base = inbox["url"].rstrip("/")
    headers = inbox.get("headers") or {}
    kind = inbox.get("type", "mailpit")
    if kind == "mailpit":
        q = urllib.parse.quote(f"to:{recipient}")
        data = json.loads(fetch(f"{base}/api/v1/search?query={q}&limit=5", headers))
        for msg in data.get("messages", []):
            if parse_time(msg.get("Created", "")) >= since - 2:
                full = json.loads(fetch(f"{base}/api/v1/message/{msg['ID']}", headers))
                return (full.get("Text") or "") + "\n" + (full.get("HTML") or "")
        return None
    if kind == "mailhog":
        q = urllib.parse.quote(recipient)
        data = json.loads(fetch(f"{base}/api/v2/search?kind=to&query={q}&limit=5", headers))
        for item in data.get("items", []):
            if parse_time(item.get("Created", "")) >= since - 2:
                return item.get("Content", {}).get("Body", "")
        return None
    if kind == "http":
        url = inbox["url"].replace("{{email}}", urllib.parse.quote(recipient))
        body = fetch(url, headers)
        return body or None
    raise SystemExit(f"auth.inbox.type desconhecido: {kind}")


def extract(kind: str, body: str, inbox: dict) -> str | None:
    text = html.unescape(body.replace("=\r\n", "").replace("=\n", "").replace("=3D", "="))
    pattern = inbox["linkPattern"] if kind == "link" else inbox["codePattern"]
    matches = re.findall(pattern, text)
    if not matches:
        return None
    if kind == "link":
        ignored = ("unsubscribe", ".png", ".jpg", ".gif", "fonts.", "w3.org")
        matches = [m for m in matches if not any(i in m.lower() for i in ignored)] or matches
    value = matches[0]
    return value if isinstance(value, str) else value[0]


def main() -> int:
    if len(sys.argv) < 3 or sys.argv[1] not in ("link", "code"):
        print(__doc__)
        return 2
    kind, recipient = sys.argv[1], sys.argv[2]
    since = float(sys.argv[sys.argv.index("--since") + 1]) if "--since" in sys.argv else 0.0
    inbox = cfgmod.load()["auth"]["inbox"]
    deadline = time.time() + inbox.get("timeoutMs", 60000) / 1000
    while time.time() < deadline:
        body = latest_body(inbox, recipient, since)
        if body:
            value = extract(kind, body, inbox)
            if value:
                print(value)
                return 0
        time.sleep(2)
    print(f"[testkit] nenhum {kind} encontrado para {recipient} dentro do prazo", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
