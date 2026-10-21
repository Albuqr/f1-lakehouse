"""Teste genérico: todo módulo do projeto importa sem erro.

Copie para tests/ do projeto. Detecta erros de sintaxe, imports quebrados e
dependências faltando em módulos que nenhum outro teste exercita.
Ajuste PACKAGES se o código não estiver na raiz ou em src/.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = [ROOT / "src", ROOT]
SKIP_PARTS = {"tests", "test", "migrations", ".venv", "venv", "node_modules", "testkit", "build", "dist", "scripts"}


def _packages() -> list[str]:
    found: list[str] = []
    for base in SOURCE_DIRS:
        if not base.is_dir():
            continue
        for init in base.glob("*/__init__.py"):
            if init.parent.name not in SKIP_PARTS:
                found.append(init.parent.name)
        if found:
            break
    return found


PACKAGES = _packages()


def _modules() -> list[str]:
    names: list[str] = []
    for package in PACKAGES:
        mod = importlib.import_module(package)
        names.append(package)
        for info in pkgutil.walk_packages(mod.__path__, prefix=f"{package}."):
            if not any(part in SKIP_PARTS for part in info.name.split(".")):
                names.append(info.name)
    return names


@pytest.mark.skipif(not PACKAGES, reason="nenhum pacote Python encontrado")
@pytest.mark.parametrize("module", _modules() if PACKAGES else [])
def test_module_imports(module: str) -> None:
    importlib.import_module(module)
