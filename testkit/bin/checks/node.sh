#!/usr/bin/env bash
# Verificações estáticas e testes de projetos Node/TypeScript (inclui React Native/Expo).
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"

DIR="$PROJECT_ROOT/$(cfg node.workingDirectory .)"
cd "$DIR" || exit 2

pm="$(cfg node.packageManager auto)"
if [[ "$pm" == "auto" ]]; then
  if [[ -f pnpm-lock.yaml ]]; then pm=pnpm
  elif [[ -f yarn.lock ]]; then pm=yarn
  elif [[ -f bun.lockb || -f bun.lock ]]; then pm=bun
  else pm=npm; fi
fi
log "Gerenciador de pacotes: $pm"
if [[ "$pm" == "pnpm" || "$pm" == "yarn" ]] && ! has_cmd "$pm"; then
  has_cmd corepack && corepack enable >/dev/null 2>&1 || npm i -g "$pm" >/dev/null 2>&1
fi

has_script() { node -e "const s=require('./package.json').scripts||{};process.exit(s['$1']?0:1)" 2>/dev/null; }
run_script() { case "$pm" in npm) echo "npm run $1 --if-present";; *) echo "$pm run $1";; esac; }

# resolve NOME "scripts candidatos" "comando alternativo"
resolve() {
  local key="$1" candidates="$2" fallback="${3:-}" configured
  configured="$(cfg "node.commands.$key" auto)"
  if [[ "$configured" != "auto" ]]; then echo "$configured"; return; fi
  for s in $candidates; do if has_script "$s"; then run_script "$s"; return; fi; done
  echo "$fallback"
}

install_cmd="$(cfg node.commands.install auto)"
if [[ "$install_cmd" == "auto" ]]; then
  case "$pm" in
    pnpm) install_cmd="pnpm install --frozen-lockfile" ;;
    yarn) install_cmd="yarn install --frozen-lockfile || yarn install --immutable" ;;
    bun)  install_cmd="bun install --frozen-lockfile" ;;
    npm)  install_cmd="$([[ -f package-lock.json ]] && echo 'npm ci' || echo 'npm install')" ;;
  esac
fi

tsc_fallback=""
[[ -f tsconfig.json ]] && tsc_fallback="npx --no-install tsc --noEmit -p tsconfig.json"
prettier_fallback=""
if ls .prettierrc* prettier.config.* >/dev/null 2>&1; then prettier_fallback="npx --no-install prettier --check ."; fi

lint_cmd="$(resolve lint "lint lint:ci" "")"
format_cmd="$(resolve format "format:check fmt:check prettier:check" "$prettier_fallback")"
type_cmd="$(resolve typecheck "typecheck type-check tsc check-types types" "$tsc_fallback")"
test_cmd="$(resolve test "test:ci test:coverage test" "")"
build_cmd="$(resolve build "build" "")"

[[ "$install_cmd" != "" && "$install_cmd" != "null" ]] && shell_step "Node: instalar dependências" "$install_cmd" "$DIR"
for pair in "Node: lint|$lint_cmd" "Node: formatação|$format_cmd" "Node: tipos|$type_cmd" "Node: testes|$test_cmd" "Node: build|$build_cmd"; do
  name="${pair%%|*}"; cmd="${pair#*|}"
  if [[ -z "$cmd" || "$cmd" == "null" ]]; then skip "$name" "sem script/comando configurado"; continue; fi
  # Evita modo watch em runners de teste.
  [[ "$name" == "Node: testes" ]] && export CI=true
  shell_step "$name" "$cmd" "$DIR"
done

finish
