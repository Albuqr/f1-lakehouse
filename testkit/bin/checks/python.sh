#!/usr/bin/env bash
# Lint, formatação, tipos, testes com cobertura, SAST (bandit) e auditoria de dependências Python.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"

DIR="$PROJECT_ROOT/$(cfg python.workingDirectory .)"
cd "$DIR" || exit 2

src="$("$PYTHON_BIN" -c 'import json,sys; print(" ".join(json.loads(sys.argv[1])))' "$(cfg python.sourcePaths)")"
# bandit aceita globs separados por vírgula; cobre a pasta na raiz e em subpastas.
exclude="$("$PYTHON_BIN" -c 'import json,sys; print(",".join(p for x in json.loads(sys.argv[1]) for p in (f"./{x}", f"*/{x}/*")))' "$(cfg python.excludePaths)")"
coverage_min="$(cfg python.coverageMin 80)"

render() {
  local c="$1"
  c="${c//\{src\}/$src}"; c="${c//\{exclude\}/$exclude}"
  c="${c//\{reports\}/$REPORTS_DIR}"; c="${c//\{coverageMin\}/$coverage_min}"
  echo "$c"
}

install_cmd="$(cfg python.commands.install auto)"
if [[ "$install_cmd" == "auto" ]]; then
  if [[ -f uv.lock ]] && has_cmd uv; then install_cmd="uv sync --all-extras --dev"
  elif [[ -f poetry.lock ]]; then install_cmd="pip install poetry && poetry install --with dev || poetry install"
  elif [[ -f Pipfile.lock ]]; then install_cmd="pip install pipenv && pipenv install --dev --system --deploy"
  elif [[ -f requirements.txt ]]; then
    install_cmd="pip install -r requirements.txt"
    for f in requirements-dev.txt requirements/dev.txt dev-requirements.txt requirements-test.txt; do
      [[ -f "$f" ]] && install_cmd+=" -r $f"
    done
  elif [[ -f pyproject.toml ]]; then install_cmd="pip install -e '.[dev,test]' || pip install -e ."
  else install_cmd=""; fi
fi

if [[ -n "$install_cmd" && "$install_cmd" != "null" ]]; then
  shell_step "Python: instalar dependências do projeto" "$install_cmd" "$DIR"
fi
# Ambientes criados pelo uv/venv local passam a valer para as próximas etapas.
PIP="pip"
if [[ -x .venv/bin/python ]]; then
  export PATH="$DIR/.venv/bin:$PATH" VIRTUAL_ENV="$DIR/.venv"
  .venv/bin/python -m pip --version >/dev/null 2>&1 || PIP="uv pip"
fi
shell_step "Python: instalar ferramentas do testkit" "$PIP install -q -r '$KIT_DIR/python/requirements-testkit.txt'" "$DIR"

# Usa a configuração de referência do kit somente se o projeto não tiver a própria.
if ! grep -qs '^\[tool.ruff' pyproject.toml && [[ ! -f ruff.toml && ! -f .ruff.toml ]]; then
  export RUFF_CONFIG="$KIT_DIR/python/ruff.toml"
fi
if ! grep -qs '^\[tool.mypy' pyproject.toml && [[ ! -f mypy.ini && ! -f setup.cfg ]]; then
  export MYPY_CONFIG_FILE_DIR="$KIT_DIR/python"
fi

for key in lint format typecheck test sast audit; do
  raw="$(cfg "python.commands.$key")"
  name="Python: $key"
  if [[ -z "$raw" || "$raw" == "null" ]]; then skip "$name" "desativado na configuração"; continue; fi
  if [[ "$key" == "audit" && "$raw" == "auto" ]]; then
    # Audita as dependências declaradas do projeto, não o ambiente da máquina.
    if [[ -f requirements.txt ]]; then raw="pip-audit -r requirements.txt"
    elif [[ -f pyproject.toml ]]; then raw="pip-audit ."
    else raw="pip-audit"; fi
  fi
  cmd="$(render "$raw")"
  case "$key" in
    lint|format)
      [[ -n "${RUFF_CONFIG:-}" ]] && cmd="${cmd/ruff check/ruff check --config $RUFF_CONFIG}" && cmd="${cmd/ruff format/ruff format --config $RUFF_CONFIG}" ;;
    typecheck)
      [[ -n "${MYPY_CONFIG_FILE_DIR:-}" ]] && cmd="${cmd/mypy/mypy --config-file $KIT_DIR/python/mypy.ini}" ;;
    test)
      if [[ -z "$(find . -path ./.venv -prune -o -path ./node_modules -prune -o \( -name 'test_*.py' -o -name '*_test.py' \) -print -quit)" ]]; then
        step "$name (nenhum arquivo test_*.py encontrado)" false; continue
      fi ;;
  esac
  shell_step "$name" "$cmd" "$DIR"
done

finish
