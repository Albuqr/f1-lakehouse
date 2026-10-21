#!/usr/bin/env bash
# Sobe a aplicação (web.startCommand) quando a baseUrl é local; caso contrário usa a URL existente.
APP_PID=""

start_app() {
  local base_url start_cmd ready timeout
  base_url="$(cfg web.baseUrl)"
  start_cmd="$(cfg web.startCommand)"
  ready="${base_url%/}$(cfg web.readyPath /)"
  timeout="$(cfg web.startTimeoutSeconds 180)"
  if [[ -n "$start_cmd" && "$base_url" =~ ^https?://(localhost|127\.0\.0\.1|0\.0\.0\.0) ]] && \
     ! "$PYTHON_BIN" "$KIT_DIR/bin/lib/wait_for_url.py" "$ready" 1 >/dev/null 2>&1; then
    local setup_cmd; setup_cmd="$(cfg web.setupCommand)"
    if [[ -n "$setup_cmd" ]]; then
      log "Preparando aplicação: $setup_cmd"
      ( cd "$PROJECT_ROOT" && bash -c "$setup_cmd" ) || { fail_msg "web.setupCommand falhou"; return 1; }
    fi
    log "Subindo aplicação: $start_cmd"
    ( cd "$PROJECT_ROOT" && exec bash -c "$start_cmd" ) > "$REPORTS_DIR/app-server.log" 2>&1 &
    APP_PID=$!
  fi
  if ! "$PYTHON_BIN" "$KIT_DIR/bin/lib/wait_for_url.py" "$ready" "$timeout"; then
    [[ -f "$REPORTS_DIR/app-server.log" ]] && { warn "últimas linhas do servidor:"; tail -n 40 "$REPORTS_DIR/app-server.log"; }
    return 1
  fi
}

stop_app() {
  [[ -n "$APP_PID" ]] || return 0
  log "Encerrando aplicação (pid $APP_PID)"
  pkill -TERM -P "$APP_PID" 2>/dev/null; kill -TERM "$APP_PID" 2>/dev/null
  sleep 2; pkill -KILL -P "$APP_PID" 2>/dev/null; kill -KILL "$APP_PID" 2>/dev/null
  APP_PID=""
}
trap stop_app EXIT
