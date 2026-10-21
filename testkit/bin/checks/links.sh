#!/usr/bin/env bash
# Links quebrados na documentação (Markdown). Links do site são verificados pelo crawler web.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
cd "$PROJECT_ROOT" || exit 2

if [[ "$(cfg links.enabled true)" != "true" ]]; then skip "Links da documentação" "desativado"; finish; exit $?; fi

mapfile -t files < <("$PYTHON_BIN" - <<'PY'
import json, os, subprocess, sys, pathlib
cfg = json.loads(subprocess.check_output([sys.executable, os.path.join(os.environ["KIT_DIR"], "bin/lib/config.py"), "resolved"]))
root = pathlib.Path(os.environ["PROJECT_ROOT"])
exclude = cfg["links"]["exclude"]
seen = set()
for pattern in cfg["links"]["globs"]:
    for p in root.glob(pattern):
        rel = p.relative_to(root).as_posix()
        parts = rel.split("/")
        hidden = any(part.startswith(".") for part in parts[:-1])
        if p.is_file() and not hidden and not any(part in exclude for part in parts) and rel not in exclude and rel not in seen:
            seen.add(rel); print(rel)
PY
)

if [[ ${#files[@]} -eq 0 ]]; then skip "Links da documentação" "nenhum arquivo encontrado"; finish; exit $?; fi
log "${#files[@]} arquivo(s) de documentação"

offline=()
[[ "$(cfg links.checkExternal true)" == "true" ]] || offline=(--offline)

if has_cmd lychee; then
  step "Links da documentação (lychee)" lychee --no-progress "${offline[@]}" --max-retries 3 \
    --accept 200..=299,403,429 --format markdown --output "$REPORTS_DIR/links.md" "${files[@]}"
else
  # Alternativa sem binário: linkinator via npx.
  skip_external=()
  [[ ${#offline[@]} -gt 0 ]] && skip_external=(--skip "^https?://")
  step "Links da documentação (linkinator)" npx --yes linkinator@6 "${files[@]}" --markdown --retry "${skip_external[@]}"
fi

finish
