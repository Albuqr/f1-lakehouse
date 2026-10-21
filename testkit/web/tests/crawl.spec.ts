import { config, expect, monitor, pagesFor, test, testRoles, url } from "../src/fixtures";

const C = config.web.crawl;
test.skip(!config.web.checks.crawl, "web.checks.crawl desativado");

const origin = new URL(config.web.baseUrl).origin;
const excluded = C.excludePatterns.map((p) => new RegExp(p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"));

for (const role of testRoles()) {
  test(`links internos funcionam — ${role}`, async ({ as }) => {
    test.setTimeout(10 * 60_000);
    const page = await as(role);
    const issues = monitor(page);
    const queue = pagesFor(role).map((p) => url(p));
    const seen = new Set<string>();
    const external = new Set<string>();
    const broken: string[] = [];

    while (queue.length && seen.size < C.maxPages) {
      const target = queue.shift()!.split("#")[0];
      if (seen.has(target)) continue;
      seen.add(target);
      const res = await page.goto(target, { waitUntil: "domcontentloaded" }).catch((e: Error) => {
        broken.push(`${target} — ${e.message.split("\n")[0]}`);
        return null;
      });
      if (!res) continue;
      if (res.status() >= 400) broken.push(`${target} — HTTP ${res.status()}`);
      await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
      const hrefs = await page.$$eval("a[href]", (as) => as.map((a) => (a as HTMLAnchorElement).href));
      for (const href of hrefs) {
        if (excluded.some((r) => r.test(href))) continue;
        if (!/^https?:/.test(href)) continue;
        if (href.startsWith(origin)) { if (!seen.has(href.split("#")[0])) queue.push(href); }
        else external.add(href);
      }
    }

    if (C.checkExternalLinks) {
      for (const link of [...external].slice(0, 100)) {
        let res = await page.request.head(link, { failOnStatusCode: false, timeout: 15_000 }).catch(() => null);
        if (!res || res.status() === 405 || res.status() === 403) res = await page.request.get(link, { failOnStatusCode: false, timeout: 15_000 }).catch(() => null);
        if (!res) broken.push(`${link} — sem resposta`);
        else if (res.status() >= 400 && ![401, 403, 429].includes(res.status())) broken.push(`${link} — HTTP ${res.status()}`);
      }
    }

    test.info().annotations.push({ type: "páginas visitadas", description: String(seen.size) });
    expect(broken, "links quebrados").toEqual([]);
    expect.soft(issues.pageErrors, "exceções JavaScript durante a varredura").toEqual([]);
  });
}
