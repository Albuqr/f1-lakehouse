import { config, expect, pagesFor, test, testRoles, url } from "../src/fixtures";

const B = config.web.performance.budgets;
test.skip(!config.web.checks.performance, "web.checks.performance desativado");

for (const role of testRoles()) {
  for (const path of pagesFor(role)) {
    test(`orçamento de performance — ${role} ${path}`, async ({ as }) => {
      const page = await as(role);
      await page.addInitScript(() => {
        const w = window as unknown as { __lcp: number; __cls: number };
        w.__lcp = 0; w.__cls = 0;
        new PerformanceObserver((list) => {
          for (const e of list.getEntries()) w.__lcp = Math.max(w.__lcp, e.startTime);
        }).observe({ type: "largest-contentful-paint", buffered: true });
        new PerformanceObserver((list) => {
          for (const e of list.getEntries() as (PerformanceEntry & { value: number; hadRecentInput: boolean })[]) {
            if (!e.hadRecentInput) w.__cls += e.value;
          }
        }).observe({ type: "layout-shift", buffered: true });
      });
      await page.goto(url(path), { waitUntil: "load" });
      await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => undefined);
      await page.waitForTimeout(1000);

      const m = await page.evaluate(() => {
        const nav = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming;
        const resources = performance.getEntriesByType("resource") as PerformanceResourceTiming[];
        const w = window as unknown as { __lcp: number; __cls: number };
        const size = (r: PerformanceResourceTiming) => r.transferSize || r.encodedBodySize || 0;
        return {
          ttfbMs: nav.responseStart - nav.startTime,
          domContentLoadedMs: nav.domContentLoadedEventEnd - nav.startTime,
          loadMs: nav.loadEventEnd - nav.startTime,
          lcpMs: w.__lcp,
          cls: w.__cls,
          totalTransferKb: (resources.reduce((s, r) => s + size(r), 0) + (nav.transferSize || 0)) / 1024,
          jsTransferKb: resources.filter((r) => r.initiatorType === "script" || /\.m?js(\?|$)/.test(r.name)).reduce((s, r) => s + size(r), 0) / 1024,
        };
      });
      await test.info().attach("metricas.json", { body: JSON.stringify(m, null, 2), contentType: "application/json" });
      for (const [key, budget] of Object.entries(B) as [keyof typeof B, number][]) {
        if (!budget) continue;
        const value = m[key];
        if (key === "lcpMs" && value === 0) continue; // navegador sem suporte a LCP
        expect.soft(Math.round(value * 1000) / 1000, `${key} acima do orçamento (${budget})`).toBeLessThanOrEqual(budget);
      }
    });
  }
}
