import type { Page, Response } from "@playwright/test";
import { config, expect, looksLikeLogin, test, testRoles, url } from "../src/fixtures";
import type { AccessRule } from "../src/config";

/*
 * Matriz de permissões. Exemplo em testkit.config.json:
 *   "rules":    [{ "path": "/admin", "allow": ["admin"], "deny": ["user", "anonymous"] }]
 *   "apiRules": [{ "method": "GET", "path": "/api/users", "allow": ["admin"], "deny": ["user", "anonymous"] }]
 * Papéis que não aparecem em allow/deny não são testados naquela regra.
 */
const A = config.auth;
const available = new Set(testRoles());
test.skip(!config.web.checks.authorization || (A.rules.length === 0 && A.apiRules.length === 0), "defina auth.rules / auth.apiRules");

async function pageDenied(page: Page, response: Response | null, rule: AccessRule): Promise<boolean> {
  if (response && [401, 403, 404].includes(response.status())) return true;
  if (looksLikeLogin(page)) return true;
  if (rule.deniedSelector && (await page.locator(rule.deniedSelector).first().isVisible().catch(() => false))) return true;
  // Redirecionado para outro lugar (ex.: home) também conta como negado.
  return new URL(page.url()).pathname.replace(/\/$/, "") !== rule.path.split("?")[0].replace(/\/$/, "");
}

for (const rule of A.rules) {
  test.describe(`página ${rule.path}`, () => {
    for (const role of rule.allow ?? []) {
      test(`${role} tem acesso`, async ({ as }) => {
        test.skip(!available.has(role), `papel ${role} sem sessão`);
        const page = await as(role);
        const res = await page.goto(url(rule.path));
        await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => undefined);
        expect(res?.status() ?? 0, `status para ${role}`).toBeLessThan(400);
        expect(looksLikeLogin(page), `${role} foi mandado ao login`).toBe(false);
        if (rule.expectSelector) await expect(page.locator(rule.expectSelector).first()).toBeVisible();
      });
    }
    for (const role of rule.deny ?? []) {
      test(`${role} é bloqueado`, async ({ as }) => {
        test.skip(!available.has(role), `papel ${role} sem sessão`);
        const page = await as(role);
        const res = await page.goto(url(rule.path));
        await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => undefined);
        expect(await pageDenied(page, res, rule), `${role} conseguiu abrir ${rule.path} (url final ${page.url()})`).toBe(true);
        if (rule.expectSelector) await expect(page.locator(rule.expectSelector)).toHaveCount(0);
      });
    }
  });
}

for (const rule of A.apiRules) {
  const method = (rule.method ?? "GET").toUpperCase();
  test.describe(`API ${method} ${rule.path}`, () => {
    const call = async (page: Page) =>
      page.request.fetch(url(rule.path), { method, data: rule.body, maxRedirects: 0, failOnStatusCode: false });
    for (const role of rule.allow ?? []) {
      test(`${role} é autorizado`, async ({ as }) => {
        test.skip(!available.has(role), `papel ${role} sem sessão`);
        const page = await as(role);
        await page.goto(url("/")).catch(() => undefined); // tokens em localStorage não chegam à API; use header/cookie
        const res = await call(page);
        expect(res.status(), `${role} recebeu ${res.status()}`).toBeLessThan(400);
      });
    }
    for (const role of rule.deny ?? []) {
      test(`${role} recebe 401/403`, async ({ as }) => {
        test.skip(!available.has(role), `papel ${role} sem sessão`);
        const page = await as(role);
        const res = await call(page);
        expect([401, 403, 404], `${role} recebeu ${res.status()} em ${method} ${rule.path}`).toContain(res.status());
      });
    }
  });
}
