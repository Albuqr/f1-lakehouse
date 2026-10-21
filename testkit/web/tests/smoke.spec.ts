import { config, expect, expectNoIssues, looksLikeLogin, monitor, pagesFor, test, testRoles, url } from "../src/fixtures";

test.skip(!config.web.checks.smoke, "web.checks.smoke desativado");

for (const role of testRoles()) {
  test.describe(`fumaça — ${role}`, () => {
    for (const path of pagesFor(role)) {
      test(`abre ${path} sem erros`, async ({ as }) => {
        const page = await as(role);
        const issues = monitor(page);
        const response = await page.goto(url(path), { waitUntil: "load" });
        await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => undefined);

        expect(response, `sem resposta para ${path}`).not.toBeNull();
        expect(response!.status(), `status HTTP de ${path}`).toBeLessThan(400);
        if (role !== "anonymous") expect(looksLikeLogin(page), `${role} foi mandado ao login ao abrir ${path}`).toBe(false);

        await expect(page.locator("body")).toBeVisible();
        const text = (await page.locator("body").innerText()).trim();
        expect(text.length, `${path} renderizou página vazia`).toBeGreaterThan(0);
        expect(await page.title(), `${path} sem <title>`).not.toBe("");
        expectNoIssues(issues, path);
      });
    }
  });
}

test("página inexistente não quebra o servidor", async ({ request }) => {
  const res = await request.get(url(`/testkit-pagina-inexistente-${Date.now()}`));
  expect(res.status(), "rota inexistente gerou erro 5xx").toBeLessThan(500);
  if (res.status() === 200) {
    test.info().annotations.push({
      type: "aviso",
      description: "Rota inexistente responde 200 (comum em SPAs). Considere exibir uma página 404 clara.",
    });
  }
});
