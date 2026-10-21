#!/usr/bin/env bash
# Segurança do código: segredos vazados, análise estática (SAST) e dependências vulneráveis.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
cd "$PROJECT_ROOT" || exit 2

BIN_DIR="$KIT_DIR/.bin"; mkdir -p "$BIN_DIR"; export PATH="$BIN_DIR:$PATH"
GITLEAKS_VERSION="${GITLEAKS_VERSION:-8.21.2}"
OSV_VERSION="${OSV_VERSION:-2.3.3}"
arch="$(uname -m)"; [[ "$arch" == "x86_64" ]] && arch_gl="x64" || arch_gl="arm64"
[[ "$arch" == "x86_64" ]] && arch_osv="amd64" || arch_osv="arm64"
os="$(uname -s | tr '[:upper:]' '[:lower:]')"

ensure_gitleaks() {
  has_cmd gitleaks && return 0
  log "Baixando gitleaks $GITLEAKS_VERSION"
  curl -sSfL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_${os}_${arch_gl}.tar.gz" \
    | tar -xz -C "$BIN_DIR" gitleaks
}
ensure_osv() {
  has_cmd osv-scanner && return 0
  log "Baixando osv-scanner $OSV_VERSION"
  curl -sSfL -o "$BIN_DIR/osv-scanner" "https://github.com/google/osv-scanner/releases/download/v${OSV_VERSION}/osv-scanner_${os}_${arch_osv}" \
    && chmod +x "$BIN_DIR/osv-scanner"
}
# Compatível com osv-scanner v1 e v2; código 128 = nenhum lockfile encontrado (não é falha).
run_osv() {
  local code=0
  if osv-scanner --version 2>&1 | grep -q "version: 1\."; then
    osv-scanner --recursive --skip-git --format table "$PROJECT_ROOT" || code=$?
  else
    osv-scanner scan source --recursive --format table "$PROJECT_ROOT" || code=$?
  fi
  [[ $code -eq 128 ]] && { warn "osv-scanner: nenhum arquivo de dependências encontrado"; return 0; }
  return $code
}
ensure_semgrep() { has_cmd semgrep || pip install -q semgrep; }

if [[ "$(cfg security.secrets true)" == "true" ]]; then
  if ensure_gitleaks; then
    args=(--redact --report-format sarif --report-path "$REPORTS_DIR/gitleaks.sarif" --exit-code 1)
    allow="$(cfg security.allowlistFile)"; [[ -n "$allow" ]] && args+=(--config "$PROJECT_ROOT/$allow")
    if [[ -d .git ]]; then
      step "Segurança: segredos no histórico git (gitleaks)" gitleaks git "${args[@]}" .
    else
      step "Segurança: segredos nos arquivos (gitleaks)" gitleaks dir "${args[@]}" .
    fi
  else
    step "Segurança: instalar gitleaks" false
  fi
else skip "Segurança: segredos" "desativado"; fi

if [[ "$(cfg security.sast true)" == "true" ]]; then
  if ensure_semgrep; then
    step "Segurança: SAST (semgrep $(cfg security.semgrepConfig p/default))" \
      semgrep scan --config "$(cfg security.semgrepConfig p/default)" --error --metrics=off \
      --exclude testkit --exclude node_modules --exclude .venv --exclude testkit.yml \
      --sarif --output "$REPORTS_DIR/semgrep.sarif"
  else step "Segurança: instalar semgrep" false; fi
else skip "Segurança: SAST" "desativado"; fi

if [[ "$(cfg security.dependencies true)" == "true" ]]; then
  level="$(cfg security.auditLevel high)"
  if [[ -f pnpm-lock.yaml ]]; then shell_step "Segurança: dependências Node (pnpm audit)" "pnpm audit --audit-level=$level --prod"
  elif [[ -f yarn.lock ]]; then shell_step "Segurança: dependências Node (yarn audit)" "yarn npm audit --severity $level 2>/dev/null || yarn audit --level $level --groups dependencies"
  elif [[ -f package-lock.json ]]; then shell_step "Segurança: dependências Node (npm audit)" "npm audit --audit-level=$level --omit=dev"
  fi
  # osv-scanner cobre todos os lockfiles (npm, pip, poetry, Gradle, CocoaPods, pub, Go, Cargo...).
  if ensure_osv; then
    step "Segurança: dependências em todos os ecossistemas (osv-scanner)" run_osv
  else step "Segurança: instalar osv-scanner" false; fi
else skip "Segurança: dependências" "desativado"; fi

finish
