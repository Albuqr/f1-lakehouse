import AxeBuilder from "@axe-core/playwright";
import { config, expect, pagesFor, test, testRoles, url } from "../src/fixtures";

const cfg = config.web.accessibility;
test.skip(!config.web.checks.accessibility, "web.checks.accessibility desativado");

for (const role of testRoles()) {
  for (const path of pagesFor(role)) {
    test(`acessibilidade (${cfg.tags.join(", ")}) — ${role} ${path}`, async ({ as }) => {
      const page = await as(role);
      await page.goto(url(path));
      await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => undefined);

      let builder = new AxeBuilder({ page }).withTags(cfg.tags);
      if (cfg.disableRules.length) builder = builder.disableRules(cfg.disableRules);
      for (const selector of cfg.exclude) builder = builder.exclude(selector);
      const results = await builder.analyze();

      const blocking = results.violations.filter((v) => cfg.failOnImpacts.includes(v.impact ?? ""));
      const minor = results.violations.filter((v) => !cfg.failOnImpacts.includes(v.impact ?? ""));
      for (const v of minor) {
        test.info().annotations.push({ type: `a11y ${v.impact}`, description: `${v.id}: ${v.help} (${v.nodes.length} elemento(s))` });
      }
      await test.info().attach("axe-results.json", { body: JSON.stringify(results.violations, null, 2), contentType: "application/json" });

      const report = blocking.map(
        (v) => `[${v.impact}] ${v.id}: ${v.help}\n  ${v.helpUrl}\n  ${v.nodes.slice(0, 5).map((n) => n.target.join(" ")).join("\n  ")}`,
      );
      expect(report, `violações de acessibilidade em ${path}`).toEqual([]);
    });
  }
}

test("navegação por teclado alcança elementos interativos", async ({ page }) => {
  await page.goto(url(config.web.publicPages[0] ?? "/"));
  const interactive = await page.locator("a[href], button, input, select, textarea, [tabindex]:not([tabindex='-1'])").count();
  test.skip(interactive === 0, "página sem elementos interativos");
  const focused = new Set<string>();
  for (let i = 0; i < Math.min(interactive, 15); i++) {
    await page.keyboard.press("Tab");
    const tag = await page.evaluate(() => {
      const el = document.activeElement;
      return el && el !== document.body ? el.outerHTML.slice(0, 120) : "";
    });
    if (tag) focused.add(tag);
  }
  expect(focused.size, "Tab não move o foco entre elementos").toBeGreaterThan(0);
  // Foco precisa ser visível (contorno ou sombra).
  const visibleFocus = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body) return true;
    const s = getComputedStyle(el);
    return (s.outlineStyle !== "none" && s.outlineWidth !== "0px") || s.boxShadow !== "none";
  });
  expect.soft(visibleFocus, "elemento focado sem indicação visual de foco").toBe(true);
});
