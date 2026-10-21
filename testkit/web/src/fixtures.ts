import { test as base, expect, type BrowserContext, type Page } from "@playwright/test";
import { config, url } from "./config";
import { roles } from "./auth/credentials";
import { contextOptionsFor, sessionMeta } from "./auth/login";

export interface PageIssues {
  consoleErrors: string[];
  pageErrors: string[];
  failedRequests: string[];
}

const ignoredConsole = config.web.ignoreConsoleErrors.map((p) => new RegExp(p, "i"));
const ignoredRequests = config.web.ignoreRequestFailures.map((p) => new RegExp(p, "i"));

/** Registra erros de console, exceções não tratadas e requisições com falha/5xx. */
export function monitor(page: Page): PageIssues {
  const issues: PageIssues = { consoleErrors: [], pageErrors: [], failedRequests: [] };
  page.on("console", (msg) => {
    if (msg.type() === "error" && !ignoredConsole.some((r) => r.test(msg.text()))) issues.consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => issues.pageErrors.push(`${err.name}: ${err.message}`));
  page.on("requestfailed", (req) => {
    const reason = req.failure()?.errorText ?? "";
    if (/ERR_ABORTED|NS_BINDING_ABORTED|cancelled/i.test(reason)) return; // navegação interrompida não é erro
    if (!ignoredRequests.some((r) => r.test(req.url()))) issues.failedRequests.push(`${req.method()} ${req.url()} — ${reason}`);
  });
  page.on("response", (res) => {
    if (res.status() >= 500 && !ignoredRequests.some((r) => r.test(res.url()))) {
      issues.failedRequests.push(`${res.request().method()} ${res.url()} — HTTP ${res.status()}`);
    }
  });
  return issues;
}

export function expectNoIssues(issues: PageIssues, where: string) {
  expect.soft(issues.pageErrors, `exceções JavaScript em ${where}`).toEqual([]);
  expect.soft(issues.consoleErrors, `erros de console em ${where}`).toEqual([]);
  expect.soft(issues.failedRequests, `requisições com falha em ${where}`).toEqual([]);
}

/** Papéis testáveis: anônimo + papéis com sessão criada no setup. */
export function testRoles(): string[] {
  return ["anonymous", ...roles().map((r) => r.name)];
}

/** Páginas que cada papel deve conseguir abrir. */
export function pagesFor(role: string): string[] {
  const set = new Set<string>();
  if (role === "anonymous") config.web.publicPages.forEach((p) => set.add(p));
  else {
    const r = config.auth.roles.find((x) => x.name === role);
    if (r?.homePath) set.add(r.homePath);
    r?.pages?.forEach((p) => set.add(p));
  }
  for (const rule of config.auth.rules) if (rule.allow?.includes(role) && !rule.path.includes(":")) set.add(rule.path);
  return [...set];
}

export function looksLikeLogin(page: Page): boolean {
  return new RegExp(config.auth.redirectToLoginPattern, "i").test(new URL(page.url()).pathname + new URL(page.url()).search);
}

type Fixtures = {
  /** Abre uma página nova autenticada como o papel informado ("anonymous" para visitante). */
  as: (role: string) => Promise<Page>;
};

export const test = base.extend<Fixtures>({
  as: async ({ browser }, use) => {
    const contexts: BrowserContext[] = [];
    await use(async (role: string) => {
      const context = await browser.newContext(contextOptionsFor(role));
      const meta = role === "anonymous" ? undefined : sessionMeta(role);
      if (meta?.sessionStorage) {
        await context.addInitScript((items: Record<string, string>) => {
          for (const [k, v] of Object.entries(items)) window.sessionStorage.setItem(k, v);
        }, meta.sessionStorage);
      }
      context.setDefaultNavigationTimeout(config.web.navigationTimeoutMs);
      contexts.push(context);
      return context.newPage();
    });
    await Promise.all(contexts.map((c) => c.close()));
  },
});

export { expect, url, config };
