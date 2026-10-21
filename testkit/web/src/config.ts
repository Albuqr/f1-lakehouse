/**
 * Lê a configuração final pelo mesmo carregador usado nos scripts (bin/lib/config.py),
 * garantindo que padrões, testkit.config.json e variáveis ${VAR} tenham a mesma semântica.
 */
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
export const KIT_DIR = path.resolve(here, "..", "..");

export type Action =
  | { goto: string }
  | { fill: string; value: string }
  | { click: string }
  | { press: string; key: string }
  | { check: string }
  | { select: string; value: string }
  | { waitForUrl: string }
  | { waitForSelector: string }
  | { emailLink: true }
  | { fillEmailCode: string }
  | { wait: number };

export interface RoleConfig {
  name: string;
  envPrefix: string;
  homePath?: string;
  pages?: string[];
  strategy?: string;
  steps?: Action[];
}

export interface AccessRule {
  path: string;
  method?: string;
  allow?: string[];
  deny?: string[];
  expectSelector?: string;
  deniedSelector?: string;
  body?: unknown;
}

export interface TestkitConfig {
  reportsDir: string;
  web: {
    baseUrl: string;
    browsers: string[];
    retries: number;
    workers: number;
    navigationTimeoutMs: number;
    publicPages: string[];
    ignoreConsoleErrors: string[];
    ignoreRequestFailures: string[];
    checks: Record<"smoke" | "auth" | "authorization" | "accessibility" | "security" | "responsive" | "performance" | "crawl", boolean>;
    accessibility: { tags: string[]; failOnImpacts: string[]; disableRules: string[]; exclude: string[] };
    security: {
      requiredHeaders: string[];
      requireFrameProtection: boolean;
      requireHstsOnHttps: boolean;
      forbiddenHeaders: string[];
      sensitivePaths: string[];
      checkCors: boolean;
      checkSessionCookies: boolean;
      checkMixedContent: boolean;
    };
    responsive: { viewports: { name: string; width: number; height: number }[]; minTapTargetPx: number };
    performance: {
      budgets: Record<"ttfbMs" | "domContentLoadedMs" | "loadMs" | "lcpMs" | "cls" | "totalTransferKb" | "jsTransferKb", number>;
    };
    crawl: { maxPages: number; checkExternalLinks: boolean; excludePatterns: string[] };
  };
  auth: {
    strategy: string;
    loginPath: string;
    success: { urlPattern: string; selector: string; timeoutMs: number };
    failure: { selector: string; checkInvalidLogin: boolean };
    redirectToLoginPattern: string;
    form: { usernameSelector: string; passwordSelector: string; submitSelector: string; twoStep: boolean; nextSelector: string };
    mfa: { codeSelector: string; submitSelector: string };
    magicLink: { emailSelector: string; submitSelector: string; mode: "link" | "code" };
    oauth: {
      providerButtonSelector: string;
      providerUsernameSelector: string;
      providerNextSelector: string;
      providerPasswordSelector: string;
      providerSubmitSelector: string;
      consentSelector: string;
      providerHostPattern: string;
    };
    api: {
      method: string;
      path: string;
      contentType: "json" | "form";
      body: Record<string, unknown>;
      tokenJsonPath: string;
      tokenStorage: "cookies" | "localStorage" | "sessionStorage" | "header";
      storageKey: string;
      headerName: string;
      headerPrefix: string;
      mfa: null | { path: string; body: Record<string, unknown> };
    };
    bearer: { storage: "header" | "localStorage" | "sessionStorage"; headerName: string; headerPrefix: string; storageKey: string };
    cookie: { name: string; domain: string; path: string; httpOnly: boolean; secure: boolean; sameSite: "Lax" | "Strict" | "None" };
    steps: Action[];
    logout: { path: string; selector: string; method: "ui" | "get" | "post" };
    roles: RoleConfig[];
    rules: AccessRule[];
    apiRules: AccessRule[];
  };
}

let cached: TestkitConfig | undefined;

export function loadConfig(): TestkitConfig {
  if (cached) return cached;
  const python = process.env.PYTHON_BIN || (process.platform === "win32" ? "python" : "python3");
  const out = execFileSync(python, [path.join(KIT_DIR, "bin", "lib", "config.py"), "resolved"], {
    encoding: "utf-8",
    env: process.env,
  });
  cached = JSON.parse(out) as TestkitConfig & { _meta: { projectRoot: string } };
  return cached;
}

export const config = loadConfig();
export const PROJECT_ROOT: string = (config as unknown as { _meta: { projectRoot: string } })._meta.projectRoot;
export const REPORTS_DIR = path.resolve(PROJECT_ROOT, config.reportsDir);
export const AUTH_DIR = path.join(REPORTS_DIR, ".auth");

export function url(p: string): string {
  if (/^https?:\/\//.test(p)) return p;
  return config.web.baseUrl.replace(/\/$/, "") + (p.startsWith("/") ? p : `/${p}`);
}

export const UI_STRATEGIES = new Set(["form", "form-totp", "form-email-code", "magic-link", "oauth", "steps"]);
