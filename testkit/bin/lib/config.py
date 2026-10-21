#!/usr/bin/env python3
"""Carrega e valida a configuração do testkit.

Uso:
  config.py resolved            -> imprime o JSON final (padrões + projeto + variáveis)
  config.py get caminho.a.b [p] -> imprime um valor (listas/objetos em JSON)
  config.py validate            -> valida e lista problemas (exit 1 se houver erros)

Ordem de precedência: defaults.json < testkit.config.json < variáveis TESTKIT_*.
Strings aceitam ${VAR} e ${VAR:-padrão}.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

KIT_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(os.environ.get("TESTKIT_PROJECT_ROOT", KIT_DIR.parent)).resolve()

AUTH_STRATEGIES = {
    "none",
    "form",
    "form-totp",
    "form-email-code",
    "magic-link",
    "oauth",
    "steps",
    "api",
    "bearer",
    "cookie",
    "basic",
    "storage-state",
}
ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def config_path() -> Path:
    explicit = os.environ.get("TESTKIT_CONFIG")
    if explicit:
        return Path(explicit).resolve()
    return PROJECT_ROOT / "testkit.config.json"


def deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            if key.startswith("$"):
                continue
            merged[key] = deep_merge(base.get(key), value) if key in base else value
        return merged
    return override


def interpolate(value: Any) -> Any:
    if isinstance(value, str):
        return ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1)) or (m.group(2) or ""), value)
    if isinstance(value, list):
        return [interpolate(v) for v in value]
    if isinstance(value, dict):
        return {k: interpolate(v) for k, v in value.items()}
    return value


def load() -> dict[str, Any]:
    defaults = json.loads((KIT_DIR / "defaults.json").read_text(encoding="utf-8"))
    path = config_path()
    user: dict[str, Any] = {}
    if path.exists():
        try:
            user = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            sys.exit(f"[testkit] JSON inválido em {path}: {exc}")
    cfg = interpolate(deep_merge(defaults, user))
    # Atalhos por variável de ambiente (úteis em CI).
    if os.environ.get("TESTKIT_BASE_URL"):
        cfg["web"]["baseUrl"] = os.environ["TESTKIT_BASE_URL"]
    if os.environ.get("TESTKIT_AUTH_STRATEGY"):
        cfg["auth"]["strategy"] = os.environ["TESTKIT_AUTH_STRATEGY"]
    cfg["_meta"] = {
        "projectRoot": str(PROJECT_ROOT),
        "kitDir": str(KIT_DIR),
        "configFile": str(path),
        "configFound": path.exists(),
    }
    return cfg


def get(cfg: dict[str, Any], dotted: str, default: Any = None) -> Any:
    node: Any = cfg
    for part in dotted.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return default
    return node


def validate(cfg: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not cfg["_meta"]["configFound"]:
        warnings.append(f"{cfg['_meta']['configFile']} não encontrado; usando apenas os padrões.")
    auth = cfg["auth"]
    roles = auth.get("roles") or []
    strategies = {auth.get("strategy")} | {r.get("strategy") for r in roles if r.get("strategy")}
    for strategy in strategies:
        if strategy not in AUTH_STRATEGIES:
            errors.append(f"auth.strategy inválida: {strategy!r}. Use uma de: {', '.join(sorted(AUTH_STRATEGIES))}")
    names = [r.get("name") for r in roles]
    if len(names) != len(set(names)):
        errors.append("auth.roles possui nomes repetidos.")
    if "anonymous" in names:
        errors.append("'anonymous' é reservado para visitantes sem login; não declare como papel.")
    for role in roles:
        if not role.get("name") or not re.fullmatch(r"[a-zA-Z0-9_-]+", role["name"]):
            errors.append(f"Papel com nome inválido: {role!r}")
        if not role.get("envPrefix"):
            errors.append(f"Papel {role.get('name')!r} precisa de envPrefix.")
    known = set(names) | {"anonymous"}
    for kind in ("rules", "apiRules"):
        for rule in auth.get(kind) or []:
            if not rule.get("path"):
                errors.append(f"auth.{kind}: regra sem path: {rule!r}")
            for role in (rule.get("allow") or []) + (rule.get("deny") or []):
                if role not in known:
                    errors.append(f"auth.{kind}: papel desconhecido {role!r} em {rule.get('path')}")
    if "steps" in strategies and not auth.get("steps"):
        errors.append("auth.strategy=steps exige auth.steps com a sequência de ações.")
    if "oauth" in strategies and not auth["oauth"].get("providerButtonSelector"):
        errors.append("auth.strategy=oauth exige auth.oauth.providerButtonSelector.")
    if auth.get("strategy") not in (None, "none") and not roles:
        errors.append("Há estratégia de login mas nenhum papel em auth.roles.")
    if (
        cfg["web"].get("enabled") is not False
        and auth.get("strategy") in ("form", "form-totp", "form-email-code", "oauth")
        and not (auth["success"].get("urlPattern") or auth["success"].get("selector"))
    ):
        warnings.append("Defina auth.success.urlPattern ou auth.success.selector para confirmar o login com precisão.")
    base_url = cfg["web"].get("baseUrl", "")
    if base_url and not re.match(r"^https?://", base_url):
        errors.append(f"web.baseUrl precisa começar com http:// ou https:// (atual: {base_url!r}).")
    coverage = cfg["python"].get("coverageMin")
    if not isinstance(coverage, (int, float)) or not 0 <= coverage <= 100:
        errors.append("python.coverageMin deve ser um número entre 0 e 100.")
    return errors, warnings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cfg = load()
    command = argv[1]
    if command == "resolved":
        print(json.dumps(cfg, indent=2, ensure_ascii=False))
        return 0
    if command == "get":
        if len(argv) < 3:
            print("uso: config.py get caminho [padrão]", file=sys.stderr)
            return 2
        value = get(cfg, argv[2], argv[3] if len(argv) > 3 else "")
        if isinstance(value, (dict, list)):
            print(json.dumps(value, ensure_ascii=False))
        elif isinstance(value, bool):
            print("true" if value else "false")
        elif value is None:
            print("")
        else:
            print(value)
        return 0
    if command == "validate":
        errors, warnings = validate(cfg)
        for w in warnings:
            print(f"[aviso] {w}")
        for e in errors:
            print(f"[erro] {e}")
        if not errors:
            print("[ok] configuração válida")
        return 1 if errors else 0
    print(f"comando desconhecido: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
