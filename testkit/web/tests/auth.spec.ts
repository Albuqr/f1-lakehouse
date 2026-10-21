import { config, UI_STRATEGIES, url } from "../src/config";
import { credentialsFor, roles, strategyFor } from "../src/auth/credentials";
import { establishSession, loginThroughUi, logout, presetActions, runActions } from "../src/auth/login";
import { expect, looksLikeLogin, test } from "../src/fixtures";

const A = config.auth;
test.skip(!config.web.checks.auth || roles().length === 0, "sem login configurado (auth.strategy=none)");

for (const role of roles()) {
  const strategy = strategyFor(role);
  const usesPassword = ["form", "form-totp", "form-email-code", "oauth"].includes(strategy);
  const home = role.homePath || "/";

  test.describe(`login — ${role.name} (${strategy})`, () => {
    test("senha incorreta é recusada", async ({ browser }) => {
      test.skip(!usesPassword || !A.failure.checkInvalidLogin, "estratégia sem senha ou checagem desativada");
      const context = await browser.newContext();
      const page = await context.newPage();
      const creds = { ...credentialsFor(role), password: `senha-errada-${Date.now()}` };
      await page.goto(url(A.loginPath));
      await runActions(page, presetActions(strategy, role, true), creds);
      if (A.failure.selector) {
        await expect(page.locator(A.failure.selector).first(), "mensagem de erro de login").toBeVisible();
      } else {
        await page.waitForTimeout(3000);
      }
      // Não pode ter chegado à área logada.
      await page.goto(url(home));
      expect(looksLikeLogin(page) || (await page.locator("input[type=password]").count()) > 0, "senha errada permitiu acesso").toBe(true);
      await context.close();
    });

    test("sessão continua válida após recarregar", async ({ as }) => {
      const page = await as(role.name);
      await page.goto(url(home));
      await page.reload();
      expect(looksLikeLogin(page), "sessão perdida após recarregar").toBe(false);
      if (A.success.selector) await expect(page.locator(A.success.selector).first()).toBeVisible();
    });

    test("sair encerra a sessão", async ({ browser }) => {
      test.skip(!A.logout.path && !A.logout.selector, "defina auth.logout.path ou auth.logout.selector");
      const cookieApi = strategy === "api" && A.api.tokenStorage === "cookies";
      test.skip(!UI_STRATEGIES.has(strategy) && !cookieApi, "sessão fixa (token/cookie/basic) não é encerrada pelo app");
      // Login próprio para não invalidar a sessão compartilhada pelos outros testes.
      let context;
      if (UI_STRATEGIES.has(strategy)) {
        context = await browser.newContext();
        await loginThroughUi(await context.newPage(), role);
      } else {
        const meta = await establishSession(browser, { ...role, name: `${role.name}-logout` });
        context = await browser.newContext({ storageState: meta.storageState });
      }
      const page = context.pages()[0] ?? (await context.newPage());
      if (!UI_STRATEGIES.has(strategy)) {
        await page.goto(url(home));
        expect(looksLikeLogin(page), "sessão via API não abriu a área logada").toBe(false);
      }
      expect(await logout(page), "logout não executado").toBe(true);
      await page.goto(url(home));
      await page.waitForLoadState("networkidle").catch(() => undefined);
      expect(looksLikeLogin(page) || (await page.locator("input[type=password]").count()) > 0, "área logada continuou acessível após sair").toBe(true);
      await context.close();
    });
  });
}

test("página de login protege o campo de senha", async ({ page }) => {
  test.skip(!roles().some((r) => ["form", "form-totp", "form-email-code"].includes(strategyFor(r))), "sem formulário de senha");
  await page.goto(url(A.loginPath));
  const password = page.locator(A.form.twoStep ? A.form.usernameSelector : A.form.passwordSelector).first();
  await expect(password).toBeVisible();
  if (!A.form.twoStep) await expect(password).toHaveAttribute("type", "password");
  if (config.web.baseUrl.startsWith("https://")) expect(page.url().startsWith("https://"), "login fora de HTTPS").toBe(true);
});
