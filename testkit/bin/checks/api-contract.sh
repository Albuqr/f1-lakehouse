#!/usr/bin/env bash
# Testes de contrato e robustez da API a partir do OpenAPI (Schemathesis — gera milhares de entradas).
# ATENÇÃO: envia requisições reais (inclusive POST/PUT). Rode apenas contra ambiente de teste.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
cd "$PROJECT_ROOT" || exit 2

openapi="$(cfg api.openapi)"
if [[ -z "$openapi" ]]; then skip "API: contrato OpenAPI" "defina api.openapi"; finish; exit $?; fi

base_url="$(cfg api.baseUrl)"; [[ -z "$base_url" ]] && base_url="$(cfg web.baseUrl)"
[[ "$openapi" =~ ^https?:// || -f "$openapi" ]] || openapi="${base_url%/}/${openapi#/}"

has_cmd schemathesis || pip install -q "schemathesis>=4,<5"

args=(run "$openapi" --url "$base_url" --checks all --max-examples "$(cfg api.maxExamples 50)"
      --report junit --report-junit-path "$REPORTS_DIR/api-contract-junit.xml")
for m in $("$PYTHON_BIN" -c 'import json,sys; print(" ".join(json.loads(sys.argv[1])))' "$(cfg api.excludeMethods)"); do
  args+=(--exclude-method "$m")
done
[[ -n "$(cfg api.includePathRegex)" ]] && args+=(--include-path-regex "$(cfg api.includePathRegex)")
[[ -n "$(cfg api.excludePathRegex)" ]] && args+=(--exclude-path-regex "$(cfg api.excludePathRegex)")

# Autenticação: token do papel configurado (api.role) ou cabeçalho livre TESTKIT_API_AUTH_HEADER.
role="$(cfg api.role)"
if [[ -n "${TESTKIT_API_AUTH_HEADER:-}" ]]; then
  args+=(-H "$TESTKIT_API_AUTH_HEADER")
elif [[ -n "$role" ]]; then
  header="$("$PYTHON_BIN" "$KIT_DIR/bin/lib/api_token.py" "$role")" || { step "API: obter token do papel $role" false; finish; exit $?; }
  if [[ -n "$header" ]]; then args+=(-H "$header"); else warn "papel '$role' sem token; rodando a API sem autenticação"; fi
fi

extra="$(cfg api.extraArgs)"
# shellcheck disable=SC2086
step "API: contrato e robustez (schemathesis)" schemathesis "${args[@]}" $extra

finish
