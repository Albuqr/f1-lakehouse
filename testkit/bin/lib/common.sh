#!/usr/bin/env bash
# Funções compartilhadas pelos scripts de verificação.
set -uo pipefail

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROJECT_ROOT="${TESTKIT_PROJECT_ROOT:-$(cd "$KIT_DIR/.." && pwd)}"
export KIT_DIR PROJECT_ROOT TESTKIT_PROJECT_ROOT="$PROJECT_ROOT"

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python || true)}"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "[testkit] Python 3 é necessário para ler a configuração." >&2
  exit 2
fi

# Carrega segredos locais/CI (.env.testkit) sem sobrescrever variáveis já definidas.
load_env_file() {
  local file="${TESTKIT_ENV_FILE:-$PROJECT_ROOT/.env.testkit}"
  [[ -f "$file" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
    local key="${line%%=*}" value="${line#*=}"
    key="$(echo "$key" | xargs)"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    value="${value%\"}"; value="${value#\"}"; value="${value%\'}"; value="${value#\'}"
    if [[ -z "${!key:-}" ]]; then export "$key=$value"; fi
  done < "$file"
}
load_env_file

cfg() { "$PYTHON_BIN" "$KIT_DIR/bin/lib/config.py" get "$@"; }

REPORTS_DIR="$PROJECT_ROOT/$(cfg reportsDir testkit-reports)"
mkdir -p "$REPORTS_DIR"
export REPORTS_DIR

if [[ -t 1 ]]; then C_RED=$'\e[31m'; C_GRN=$'\e[32m'; C_YLW=$'\e[33m'; C_BLU=$'\e[34m'; C_OFF=$'\e[0m'; else C_RED=""; C_GRN=""; C_YLW=""; C_BLU=""; C_OFF=""; fi
log()     { echo "${C_BLU}[testkit]${C_OFF} $*"; }
warn()    { echo "${C_YLW}[aviso]${C_OFF} $*"; }
fail_msg(){ echo "${C_RED}[falha]${C_OFF} $*"; }
ok_msg()  { echo "${C_GRN}[ok]${C_OFF} $*"; }

FAILED_STEPS=()
PASSED_STEPS=()
SKIPPED_STEPS=()
SUMMARY_FILE="$REPORTS_DIR/summary.md"

# step "Nome" comando... -> executa, registra resultado e continua.
step() {
  local name="$1"; shift
  log "▶ $name"
  local start=$SECONDS
  if "$@"; then
    PASSED_STEPS+=("$name"); ok_msg "$name ($((SECONDS - start))s)"
    echo "| ✅ | $name | $((SECONDS - start))s |" >> "$SUMMARY_FILE"
  else
    FAILED_STEPS+=("$name"); fail_msg "$name ($((SECONDS - start))s)"
    echo "| ❌ | $name | $((SECONDS - start))s |" >> "$SUMMARY_FILE"
    return 1
  fi
}

skip() {
  SKIPPED_STEPS+=("$1"); warn "pulado: $1${2:+ — $2}"
  echo "| ⏭️ | $1${2:+ — $2} | - |" >> "$SUMMARY_FILE"
}

# shell_step "Nome" "comando em string" -> executa via bash -c no diretório informado.
shell_step() {
  local name="$1" command="$2" dir="${3:-$PROJECT_ROOT}"
  step "$name" bash -c "cd \"$dir\" && $command"
}

finish() {
  echo
  log "Resumo: ${#PASSED_STEPS[@]} ok, ${#FAILED_STEPS[@]} falhas, ${#SKIPPED_STEPS[@]} pulados"
  for s in "${FAILED_STEPS[@]}"; do fail_msg "$s"; done
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" && -f "$SUMMARY_FILE" ]]; then
    { echo "| | Verificação | Tempo |"; echo "|---|---|---|"; cat "$SUMMARY_FILE"; } >> "$GITHUB_STEP_SUMMARY"
  fi
  [[ ${#FAILED_STEPS[@]} -eq 0 ]]
}

has_cmd() { command -v "$1" >/dev/null 2>&1; }

# ---------- Detecção de stack ----------
detect_node()   { [[ -f "$PROJECT_ROOT/$(cfg node.workingDirectory .)/package.json" ]]; }
detect_python() {
  local d="$PROJECT_ROOT/$(cfg python.workingDirectory .)"
  [[ -f "$d/pyproject.toml" || -f "$d/requirements.txt" || -f "$d/setup.py" || -f "$d/setup.cfg" || -f "$d/Pipfile" ]]
}
detect_mobile_framework() {
  local fw; fw="$(cfg mobile.framework auto)"
  if [[ "$fw" != "auto" ]]; then echo "$fw"; return; fi
  if [[ -f "$PROJECT_ROOT/pubspec.yaml" ]]; then echo flutter; return; fi
  if [[ -f "$PROJECT_ROOT/package.json" ]] && grep -q '"expo"' "$PROJECT_ROOT/package.json"; then echo expo; return; fi
  if [[ -f "$PROJECT_ROOT/package.json" ]] && grep -q '"react-native"' "$PROJECT_ROOT/package.json"; then echo react-native; return; fi
  if [[ -f "$PROJECT_ROOT/android/build.gradle" || -f "$PROJECT_ROOT/android/build.gradle.kts" || -f "$PROJECT_ROOT/build.gradle.kts" ]]; then echo android; return; fi
  if compgen -G "$PROJECT_ROOT/*.xcodeproj" >/dev/null || compgen -G "$PROJECT_ROOT/ios/*.xcodeproj" >/dev/null; then echo ios; return; fi
  echo none
}
detect_web() {
  [[ -n "$(cfg web.startCommand)" ]] || [[ -n "${TESTKIT_BASE_URL:-}" ]] || {
    [[ -f "$PROJECT_ROOT/testkit.config.json" ]] && grep -q '"baseUrl"' "$PROJECT_ROOT/testkit.config.json"
  }
}
detect_api() { [[ -n "$(cfg api.openapi)" ]]; }

# is_enabled seção funcao_deteccao -> respeita true/false/"auto".
is_enabled() {
  local value; value="$(cfg "$1.enabled" auto)"
  case "$value" in
    true) return 0 ;;
    false) return 1 ;;
    *) "$2" ;;
  esac
}

# Exporta credenciais de um papel como USERNAME/PASSWORD/TOTP_SECRET/TOKEN/EMAIL.
export_role_env() {
  local role="$1" prefix
  prefix="$("$PYTHON_BIN" - "$role" <<'PY'
import json, subprocess, sys, os
cfg = json.loads(subprocess.check_output([sys.executable, os.path.join(os.environ["KIT_DIR"], "bin/lib/config.py"), "resolved"]))
for r in cfg["auth"]["roles"]:
    if r["name"] == sys.argv[1]:
        print(r["envPrefix"]); break
PY
)"
  [[ -n "$prefix" ]] || { warn "papel '$role' não encontrado em auth.roles"; return 1; }
  local v
  for v in USERNAME PASSWORD TOTP_SECRET TOKEN EMAIL COOKIE; do
    local src="${prefix}_${v}"
    export "ROLE_${v}=${!src:-}"
  done
  [[ -z "$ROLE_EMAIL" ]] && export ROLE_EMAIL="$ROLE_USERNAME"
  return 0
}
