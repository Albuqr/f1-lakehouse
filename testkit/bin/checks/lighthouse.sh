#!/usr/bin/env bash
# Auditoria Lighthouse (performance, acessibilidade, boas práticas, SEO) com notas mínimas.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"

if [[ "$(cfg web.performance.lighthouse.enabled true)" != "true" ]]; then skip "Lighthouse" "desativado"; finish; exit $?; fi

RC="$REPORTS_DIR/lighthouserc.json"
"$PYTHON_BIN" - "$RC" <<'PY'
import json, os, subprocess, sys
cfg = json.loads(subprocess.check_output([sys.executable, os.path.join(os.environ["KIT_DIR"], "bin/lib/config.py"), "resolved"]))
web = cfg["web"]; lh = web["performance"]["lighthouse"]
base = web["baseUrl"].rstrip("/")
urls = [base + p for p in web["publicPages"]]
assertions = {f"categories:{k}": ["error", {"minScore": v}] for k, v in lh["minScores"].items()}
rc = {"ci": {
  "collect": {"url": urls, "numberOfRuns": lh["runs"], "settings": {"chromeFlags": "--no-sandbox --headless=new"}},
  "assert": {"assertions": assertions},
  "upload": {"target": "filesystem", "outputDir": os.path.join(os.environ["REPORTS_DIR"], "lighthouse")}
}}
json.dump(rc, open(sys.argv[1], "w"), indent=2)
PY

source "$KIT_DIR/bin/lib/server.sh"
if start_app; then
  step "Lighthouse: páginas públicas" npx --yes @lhci/cli@0.14 autorun --config="$RC"
else
  step "Lighthouse: aplicação respondeu" false
fi
stop_app
finish
