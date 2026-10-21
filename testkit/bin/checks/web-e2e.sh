#!/usr/bin/env bash
# Testes de navegador (Playwright): fumaça, login, permissões, acessibilidade, segurança,
# responsividade, performance e varredura de links. Uso: web-e2e.sh [args extras do playwright]
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
WEB_DIR="$KIT_DIR/web"

"$PYTHON_BIN" "$KIT_DIR/bin/lib/config.py" validate || exit 2

shell_step "Web: instalar dependências do kit" "npm install --no-audit --no-fund --loglevel=error" "$WEB_DIR"
browsers="$("$PYTHON_BIN" -c 'import json,sys; print(" ".join(json.loads(sys.argv[1])))' "$(cfg web.browsers)")"
deps_flag=""; [[ -n "${CI:-}" ]] && deps_flag="--with-deps"
shell_step "Web: instalar navegadores ($browsers)" "npx playwright install $deps_flag $browsers" "$WEB_DIR"

source "$KIT_DIR/bin/lib/server.sh"
if start_app; then
  step "Web: suíte Playwright" bash -c "cd '$WEB_DIR' && npx playwright test $*"
else
  step "Web: aplicação respondeu em $(cfg web.baseUrl)" false
fi
stop_app

log "Relatório HTML: $REPORTS_DIR/playwright-html/index.html (abra com: npx playwright show-report $REPORTS_DIR/playwright-html)"
finish
