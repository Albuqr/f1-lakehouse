import { config, expect, pagesFor, test, testRoles, url } from "../src/fixtures";

const R = config.web.responsive;
test.skip(!config.web.checks.responsive, "web.checks.responsive desativado");

for (const vp of R.viewports) {
  test.describe(`layout ${vp.name} (${vp.width}x${vp.height})`, () => {
    for (const role of testRoles()) {
      for (const path of pagesFor(role)) {
        test(`${role} ${path}`, async ({ as }) => {
          const page = await as(role);
          await page.setViewportSize({ width: vp.width, height: vp.height });
          await page.goto(url(path));
          await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => undefined);

          const overflow = await page.evaluate(() => {
            const doc = document.scrollingElement ?? document.documentElement;
            const offenders: string[] = [];
            if (doc.scrollWidth > window.innerWidth + 1) {
              for (const el of Array.from(document.body.querySelectorAll<HTMLElement>("*"))) {
                const r = el.getBoundingClientRect();
                if (r.right > window.innerWidth + 1 && r.width > 0 && getComputedStyle(el).position !== "fixed") {
                  offenders.push(`${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}${el.className && typeof el.className === "string" ? "." + el.className.split(" ").slice(0, 2).join(".") : ""}`);
                }
                if (offenders.length >= 5) break;
              }
            }
            return { scrollWidth: doc.scrollWidth, width: window.innerWidth, offenders };
          });
          expect(overflow.scrollWidth, `rolagem horizontal em ${vp.name}: ${overflow.offenders.join(", ")}`).toBeLessThanOrEqual(overflow.width + 1);

          if (vp.width < 768) {
            const meta = await page.locator('meta[name="viewport"]').getAttribute("content").catch(() => null);
            expect.soft(meta ?? "", "meta viewport ausente — o site não se adapta ao celular").toContain("width=device-width");
            if (R.minTapTargetPx > 0) {
              const small = await page.evaluate((min) => {
                return Array.from(document.querySelectorAll<HTMLElement>("a[href], button, input:not([type=hidden]), select, [role=button]"))
                  .filter((el) => {
                    const r = el.getBoundingClientRect();
                    const visible = r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden";
                    const inline = el.tagName === "A" && getComputedStyle(el).display === "inline"; // links no meio de texto são exceção (WCAG 2.5.8)
                    return visible && !inline && (r.width < min || r.height < min);
                  })
                  .slice(0, 10)
                  .map((el) => `${el.tagName.toLowerCase()} "${(el.textContent || el.getAttribute("aria-label") || "").trim().slice(0, 30)}"`);
              }, R.minTapTargetPx);
              expect.soft(small, `alvos de toque menores que ${R.minTapTargetPx}px`).toEqual([]);
            }
          }
        });
      }
    }
  });
}
