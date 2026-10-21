import fs from "node:fs";
import { config, expect, monitor, pagesFor, test, testRoles, url } from "../src/fixtures";
import { sessionMeta } from "../src/auth/login";

const S = config.web.security;
const isHttps = config.web.baseUrl.startsWith("https://");
test.skip(!config.web.checks.security, "web.checks.security desativado");

test.describe("cabeçalhos HTTP", () => {
  test("cabeçalhos de segurança presentes", async ({ request }) => {
    const res = await request.get(url("/"));
    const h = res.headers();
    for (const name of S.requiredHeaders) expect.soft(h[name.toLowerCase()], `cabeçalho ${name} ausente`).toBeTruthy();
    if (h["x-content-type-options"]) expect.soft(h["x-content-type-options"].toLowerCase()).toBe("nosniff");
    if (S.requireFrameProtection) {
      const frame = !!h["x-frame-options"] || /frame-ancestors/i.test(h["content-security-policy"] ?? "");
      expect.soft(frame, "sem proteção contra clickjacking (X-Frame-Options ou CSP frame-ancestors)").toBe(true);
    }
    if (isHttps && S.requireHstsOnHttps) {
      expect.soft(h["strict-transport-security"], "HSTS ausente").toBeTruthy();
      const maxAge = Number(/max-age=(\d+)/.exec(h["strict-transport-security"] ?? "")?.[1] ?? 0);
      expect.soft(maxAge, "HSTS max-age menor que 180 dias").toBeGreaterThanOrEqual(15552000);
    }
    for (const name of S.forbiddenHeaders) expect.soft(h[name.toLowerCase()], `cabeçalho ${name} expõe a tecnologia do servidor`).toBeFalsy();
    expect.soft(h["server"] ?? "", "cabeçalho Server expõe versão").not.toMatch(/\d+\.\d+/);
    const csp = h["content-security-policy"] ?? "";
    if (csp) expect.soft(csp, "CSP permite 'unsafe-eval' em script-src").not.toMatch(/script-src[^;]*'unsafe-eval'/);
  });

  test("método TRACE desativado", async ({ request }) => {
    const res = await request.fetch(url("/"), { method: "TRACE", failOnStatusCode: false });
    expect(res.status(), "TRACE habilitado").not.toBe(200);
  });
});

test.describe("arquivos sensíveis não expostos", () => {
  const signatures: Record<string, RegExp> = {
    ".git/config": /\[core\]/,
    ".git/HEAD": /^ref: /m,
    ".env": /^[A-Z][A-Z0-9_]+=.+/m,
    ".npmrc": /registry=|_authToken/,
    ".map": /"mappings"\s*:/,
    "docker-compose": /^services:/m,
    ".DS_Store": /Bud1/,
    "config.json": /"(password|secret|apiKey|token)"/i,
  };
  for (const path of S.sensitivePaths) {
    test(path, async ({ request }) => {
      const res = await request.get(url(path), { failOnStatusCode: false, maxRedirects: 0 });
      if (res.status() !== 200) return;
      const body = await res.text();
      const type = res.headers()["content-type"] ?? "";
      const signature = Object.entries(signatures).find(([k]) => path.includes(k))?.[1];
      const leaked = signature ? signature.test(body) : !type.includes("text/html");
      expect(leaked, `${path} está acessível publicamente`).toBe(false);
    });
  }
});

test("erros não vazam detalhes internos (stack trace, SQL)", async ({ request }) => {
  const leak = /at [\w.<>]+ \(.*:\d+:\d+\)|Traceback \(most recent call last\)|SQLSTATE|ORA-\d{5}|syntax error at or near|Exception in thread|node_modules\//;
  const probes = [
    request.get(url(`/testkit-404-${Date.now()}`), { failOnStatusCode: false }),
    request.post(url(config.auth.api.path || "/api"), { data: "{json-invalido", headers: { "content-type": "application/json" }, failOnStatusCode: false }),
    request.get(url(`/api/testkit-${Date.now()}?id=%27%22%3E%3C`), { failOnStatusCode: false }),
  ];
  for (const res of await Promise.all(probes)) {
    expect.soft(await res.text(), `${res.url()} expõe detalhes internos`).not.toMatch(leak);
  }
});

test("CORS não libera credenciais para qualquer origem", async ({ request }) => {
  test.skip(!S.checkCors, "checagem de CORS desativada");
  const evil = "https://evil.testkit.invalid";
  const targets = ["/", ...config.auth.apiRules.map((r) => r.path).slice(0, 3)];
  for (const p of targets) {
    const res = await request.get(url(p), { headers: { Origin: evil }, failOnStatusCode: false });
    const h = res.headers();
    const allowCreds = h["access-control-allow-credentials"] === "true";
    expect.soft(allowCreds && (h["access-control-allow-origin"] === evil || h["access-control-allow-origin"] === "*"), `CORS de ${p} aceita ${evil} com credenciais`).toBe(false);
  }
});

test("cookies de sessão com HttpOnly, Secure e SameSite", async () => {
  test.skip(!S.checkSessionCookies, "checagem de cookies desativada");
  const sessionLike = /sess|sid|auth|token|jwt|login|remember/i;
  const problems: string[] = [];
  let checked = 0;
  for (const role of testRoles().filter((r) => r !== "anonymous")) {
    const meta = sessionMeta(role);
    if (!meta?.storageState || meta.strategy === "cookie" || meta.strategy === "storage-state") continue;
    const state = JSON.parse(fs.readFileSync(meta.storageState, "utf-8")) as { cookies: { name: string; httpOnly: boolean; secure: boolean; sameSite: string }[] };
    for (const c of state.cookies.filter((x) => sessionLike.test(x.name))) {
      checked++;
      if (/csrf|xsrf/i.test(c.name)) continue; // token CSRF precisa ser legível pelo JS
      if (!c.httpOnly) problems.push(`${c.name}: sem HttpOnly`);
      if (isHttps && !c.secure) problems.push(`${c.name}: sem Secure`);
      if (c.sameSite === "None" && !c.secure) problems.push(`${c.name}: SameSite=None sem Secure`);
    }
  }
  test.skip(checked === 0, "nenhum cookie de sessão encontrado");
  expect(problems).toEqual([]);
});

test("sem conteúdo misto (HTTP dentro de HTTPS)", async ({ as }) => {
  test.skip(!isHttps || !S.checkMixedContent, "aplicável apenas a sites HTTPS");
  for (const role of testRoles()) {
    const page = await as(role);
    monitor(page);
    const insecure: string[] = [];
    page.on("request", (r) => { if (r.url().startsWith("http://")) insecure.push(r.url()); });
    for (const p of pagesFor(role)) await page.goto(url(p));
    expect.soft(insecure, `recursos HTTP carregados por ${role}`).toEqual([]);
  }
});
