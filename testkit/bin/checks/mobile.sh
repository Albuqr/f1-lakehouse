#!/usr/bin/env bash
# Mobile: verificações estáticas (Flutter/Android) e testes ponta a ponta com Maestro.
# Uso: mobile.sh static | mobile.sh e2e android|ios
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
cd "$PROJECT_ROOT" || exit 2

mode="${1:-static}"
platform="${2:-android}"
framework="$(detect_mobile_framework)"
log "Framework mobile: $framework"

run_static() {
  case "$framework" in
    flutter)
      shell_step "Flutter: dependências" "flutter pub get"
      shell_step "Flutter: análise estática" "$(cfg mobile.staticCommands.flutterAnalyze)"
      shell_step "Flutter: testes" "$(cfg mobile.staticCommands.flutterTest)" ;;
    android)
      local dir="."; [[ -d android ]] && dir="android"
      shell_step "Android: lint + testes unitários" "$(cfg mobile.staticCommands.androidLint)" "$PROJECT_ROOT/$dir" ;;
    expo)
      shell_step "Expo: diagnóstico do projeto (expo-doctor)" "npx --yes expo-doctor@latest" ;;
    react-native|ios|none)
      skip "Mobile: estático específico" "para RN/Expo os checks de Node já cobrem lint, tipos e testes" ;;
  esac
}

ensure_maestro() {
  has_cmd maestro && return 0
  export PATH="$HOME/.maestro/bin:$PATH"
  has_cmd maestro && return 0
  log "Instalando Maestro"
  curl -fsSL "https://get.maestro.mobile.dev" | bash && export PATH="$HOME/.maestro/bin:$PATH"
}

build_and_install() {
  local build path
  build="$(cfg "mobile.$platform.buildCommand")"
  if [[ "$platform" == "android" ]]; then path="$(cfg mobile.android.apkPath)"; else path="$(cfg mobile.ios.appPath)"; fi
  if [[ -n "$build" ]]; then shell_step "Mobile: build $platform" "$build" || return 1; fi
  [[ -n "$path" ]] || { warn "defina mobile.$platform.$([[ $platform == android ]] && echo apkPath || echo appPath)"; return 1; }
  if [[ "$platform" == "android" ]]; then
    step "Mobile: instalar APK no emulador" adb install -r "$PROJECT_ROOT/$path"
  else
    step "Mobile: instalar app no simulador" xcrun simctl install booted "$PROJECT_ROOT/$path"
  fi
}

# Executa um fluxo Maestro com as variáveis do papel e do projeto.
maestro_flow() {
  local name="$1" flow="$2"; shift 2
  local envs=(-e "APP_ID=$(cfg mobile.appId)" -e "USERNAME=${ROLE_USERNAME:-}" -e "PASSWORD=${ROLE_PASSWORD:-}" -e "EMAIL=${ROLE_EMAIL:-}")
  while IFS='=' read -r k v; do [[ -n "$k" ]] && envs+=(-e "$k=$v"); done < <("$PYTHON_BIN" -c 'import json,sys; [print(f"{k}={v}") for k,v in json.loads(sys.argv[1]).items()]' "$(cfg mobile.extraEnv)")
  envs+=("$@")
  step "Maestro: $name" maestro test "${envs[@]}" --format junit --output "$REPORTS_DIR/maestro-$(basename "$flow" .yaml).xml" "$PROJECT_ROOT/$flow"
}

run_e2e() {
  local flows; flows="$(cfg mobile.flowsDir testkit/mobile/maestro)"
  [[ -n "$(cfg mobile.appId)" ]] || { step "Mobile: mobile.appId configurado" false; return; }
  ensure_maestro || { step "Mobile: instalar Maestro" false; return; }
  build_and_install || return
  export_role_env "$(cfg mobile.role user)" || true

  local strategy; strategy="$(cfg mobile.authFlow auto)"
  [[ "$strategy" == "auto" ]] && strategy="$(cfg auth.strategy none)"

  maestro_flow "abertura do app" "$flows/smoke.yaml"
  case "$strategy" in
    none) ;;
    form) maestro_flow "login com usuário e senha" "$flows/auth/login-form.yaml" ;;
    form-totp)
      local code; code="$("$PYTHON_BIN" "$KIT_DIR/bin/lib/totp.py" "$ROLE_TOTP_SECRET" --min-remaining 20)"
      maestro_flow "login com MFA (TOTP)" "$flows/auth/login-totp.yaml" -e "TOTP_CODE=$code" ;;
    magic-link|form-email-code)
      local since; since="$(date +%s)"
      maestro_flow "solicitar link/código por e-mail" "$flows/auth/request-email-login.yaml"
      if [[ "$strategy" == "magic-link" ]]; then
        local link; link="$("$PYTHON_BIN" "$KIT_DIR/bin/lib/inbox.py" link "$ROLE_EMAIL" --since "$since")"
        maestro_flow "abrir link mágico" "$flows/auth/open-magic-link.yaml" -e "MAGIC_LINK=$link"
      else
        local code; code="$("$PYTHON_BIN" "$KIT_DIR/bin/lib/inbox.py" code "$ROLE_EMAIL" --since "$since")"
        maestro_flow "digitar código do e-mail" "$flows/auth/enter-email-code.yaml" -e "EMAIL_CODE=$code"
      fi ;;
    oauth) maestro_flow "login via provedor (OAuth/SSO)" "$flows/auth/login-oauth.yaml" ;;
    steps|api|bearer|cookie|basic|storage-state)
      warn "estratégia '$strategy' é específica de web; use mobile.authFlow para escolher um fluxo mobile" ;;
  esac
  [[ "$strategy" != "none" ]] && maestro_flow "sair da conta" "$flows/auth/logout.yaml"
  # Fluxos extras do projeto: qualquer YAML em flows/app/.
  for f in "$PROJECT_ROOT/$flows"/app/*.yaml; do
    [[ -f "$f" ]] && maestro_flow "app: $(basename "$f" .yaml)" "${f#"$PROJECT_ROOT"/}"
  done
}

case "$mode" in
  static) run_static ;;
  e2e) run_e2e ;;
  *) echo "uso: mobile.sh static | e2e android|ios"; exit 2 ;;
esac
finish
