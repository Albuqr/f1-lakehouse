import fs from "node:fs";
import path from "node:path";
import { expect, request as pwRequest, type Browser, type BrowserContextOptions, type Page } from "@playwright/test";
import { AUTH_DIR, config, url, type Action, type RoleConfig } from "../config";
import { credentialsFor, strategyFor, template, type Credentials } from "./credentials";
import { freshTotp, fromInbox } from "./otp";

const A = config.auth;

export interface SessionMeta {
  role: string;
  strategy: string;
  storageState?: string;
  extraHTTPHeaders?: Record<string, string>;
  httpCredentials?: { username: string; password: string };
  sessionStorage?: Record<string, string>;
}

// ---------------------------------------------------------------------------
// Sequências de ações (núcleo de todos os logins pela interface)
// ---------------------------------------------------------------------------

/** Monta as ações das estratégias prontas. `credentialsOnly` para antes do MFA (usado no teste de senha errada). */
export function presetActions(strategy: string, role: RoleConfig, credentialsOnly = false): Action[] {
  const f = A.form;
  const userPass: Action[] = f.twoStep
    ? [
        { fill: f.usernameSelector, value: "{{username}}" },
        { click: f.nextSelector },
        { fill: f.passwordSelector, value: "{{password}}" },
        { click: f.submitSelector },
      ]
    : [
        { fill: f.usernameSelector, value: "{{username}}" },
        { fill: f.passwordSelector, value: "{{password}}" },
        { click: f.submitSelector },
      ];
  switch (strategy) {
    case "form":
      return userPass;
    case "form-totp":
      return credentialsOnly ? userPass : [...userPass, { fill: A.mfa.codeSelector, value: "{{totp}}" }, { click: A.mfa.submitSelector }];
    case "form-email-code":
      return credentialsOnly ? userPass : [...userPass, { fillEmailCode: A.mfa.codeSelector }, { click: A.mfa.submitSelector }];
    case "magic-link": {
      const m = A.magicLink;
      const request: Action[] = [{ fill: m.emailSelector, value: "{{email}}" }, { click: m.submitSelector }];
      return m.mode === "code"
        ? [...request, { fillEmailCode: A.mfa.codeSelector }, { click: A.mfa.submitSelector }]
        : [...request, { emailLink: true }];
    }
    case "oauth": {
      const o = A.oauth;
      const actions: Action[] = [{ click: o.providerButtonSelector }];
      if (o.providerHostPattern) actions.push({ waitForUrl: o.providerHostPattern });
      actions.push({ fill: o.providerUsernameSelector, value: "{{username}}" });
      if (o.providerNextSelector) actions.push({ click: o.providerNextSelector });
      actions.push({ fill: o.providerPasswordSelector, value: "{{password}}" }, { click: o.providerSubmitSelector });
      if (o.consentSelector) actions.push({ click: o.consentSelector });
      return actions;
    }
    case "steps":
      return role.steps ?? A.steps;
    default:
      throw new Error(`Estratégia ${strategy} não usa a interface de login`);
  }
}

export async function runActions(page: Page, actions: Action[], creds: Credentials, startedAt = Date.now()): Promise<void> {
  const timeout = A.success.timeoutMs;
  for (const action of actions) {
    if ("goto" in action) await page.goto(url(template(action.goto, creds)));
    else if ("fill" in action) {
      let value = action.value;
      if (value.includes("{{totp}}")) value = value.replace("{{totp}}", await freshTotp(creds.totpSecret));
      const field = page.locator(action.fill).first();
      await field.waitFor({ state: "visible", timeout });
      await field.fill(template(value, creds));
    } else if ("click" in action) {
      const target = page.locator(action.click).first();
      await target.waitFor({ state: "visible", timeout });
      await target.click();
    } else if ("press" in action) await page.locator(action.press).first().press(action.key);
    else if ("check" in action) await page.locator(action.check).first().check();
    else if ("select" in action) await page.locator(action.select).first().selectOption(template(action.value, creds));
    else if ("waitForUrl" in action) await page.waitForURL(new RegExp(action.waitForUrl), { timeout });
    else if ("waitForSelector" in action) await page.locator(action.waitForSelector).first().waitFor({ timeout });
    else if ("emailLink" in action) await page.goto(await fromInbox("link", creds.email, startedAt));
    else if ("fillEmailCode" in action) {
      const code = await fromInbox("code", creds.email, startedAt);
      await page.locator(action.fillEmailCode).first().fill(code);
    } else if ("wait" in action) await page.waitForTimeout(action.wait);
    else throw new Error(`Ação desconhecida em auth.steps: ${JSON.stringify(action)}`);
  }
}

export async function expectLoggedIn(page: Page): Promise<void> {
  const { urlPattern, selector, timeoutMs } = A.success;
  if (urlPattern) await page.waitForURL(new RegExp(urlPattern), { timeout: timeoutMs });
  if (selector) await expect(page.locator(selector).first()).toBeVisible({ timeout: timeoutMs });
  if (!urlPattern && !selector) {
    // Sem critério explícito: saiu da página de login e não há campo de senha visível.
    await expect(page).not.toHaveURL(new RegExp(A.redirectToLoginPattern, "i"), { timeout: timeoutMs });
    await expect(page.locator("input[type=password]")).toHaveCount(0, { timeout: timeoutMs });
  }
}

export async function loginThroughUi(page: Page, role: RoleConfig, overrides: Partial<Credentials> = {}): Promise<void> {
  const creds = { ...credentialsFor(role), ...overrides };
  const startedAt = Date.now();
  await page.goto(url(A.loginPath));
  await runActions(page, presetActions(strategyFor(role), role), creds, startedAt);
  await expectLoggedIn(page);
}

// ---------------------------------------------------------------------------
// Sessões por estratégia (geradas uma vez no setup e reutilizadas pelos testes)
// ---------------------------------------------------------------------------

function sessionPath(role: string) {
  return path.join(AUTH_DIR, `${role}.session.json`);
}

function dig(obj: unknown, dotted: string): unknown {
  return dotted.split(".").reduce<unknown>((acc, k) => (acc && typeof acc === "object" ? (acc as Record<string, unknown>)[k] : undefined), obj);
}

function tokenStorage(storage: string, key: string, token: string, meta: SessionMeta, origin: string) {
  if (storage === "localStorage") {
    const file = path.join(AUTH_DIR, `${meta.role}.json`);
    const existing = meta.storageState && fs.existsSync(meta.storageState) ? JSON.parse(fs.readFileSync(meta.storageState, "utf-8")) : { cookies: [], origins: [] };
    existing.origins = [{ origin, localStorage: [{ name: key, value: token }] }];
    fs.writeFileSync(file, JSON.stringify(existing));
    meta.storageState = file;
  } else if (storage === "sessionStorage") {
    meta.sessionStorage = { [key]: token };
  }
}

export async function establishSession(browser: Browser, role: RoleConfig): Promise<SessionMeta> {
  fs.mkdirSync(AUTH_DIR, { recursive: true });
  const strategy = strategyFor(role);
  const creds = credentialsFor(role);
  const origin = new URL(config.web.baseUrl).origin;
  const meta: SessionMeta = { role: role.name, strategy };
  const stateFile = path.join(AUTH_DIR, `${role.name}.json`);

  switch (strategy) {
    case "form":
    case "form-totp":
    case "form-email-code":
    case "magic-link":
    case "oauth":
    case "steps": {
      const context = await browser.newContext();
      const page = await context.newPage();
      await loginThroughUi(page, role);
      await context.storageState({ path: stateFile });
      meta.storageState = stateFile;
      await context.close();
      break;
    }
    case "api": {
      const api = A.api;
      const ctx = await pwRequest.newContext({ baseURL: config.web.baseUrl });
      const body = template(api.body, creds);
      const send = (p: string, data: Record<string, unknown>) =>
        ctx.fetch(url(p), { method: api.method, ...(api.contentType === "form" ? { form: data as Record<string, string> } : { data }) });
      let res = await send(api.path, body);
      expect(res.status(), `login via API ${api.path} respondeu ${res.status()}: ${await res.text()}`).toBeLessThan(400);
      if (api.mfa) {
        const mfaBody = template(api.mfa.body, creds, { totp: creds.totpSecret ? await freshTotp(creds.totpSecret) : "" });
        res = await send(api.mfa.path, mfaBody);
        expect(res.status(), `MFA via API ${api.mfa.path} respondeu ${res.status()}`).toBeLessThan(400);
      }
      await ctx.storageState({ path: stateFile });
      meta.storageState = stateFile;
      if (api.tokenJsonPath) {
        const token = String(dig(await res.json(), api.tokenJsonPath) ?? "");
        expect(token, `token não encontrado em ${api.tokenJsonPath}`).not.toBe("");
        if (api.tokenStorage === "header") meta.extraHTTPHeaders = { [api.headerName]: `${api.headerPrefix}${token}` };
        else tokenStorage(api.tokenStorage, api.storageKey, token, meta, origin);
      }
      await ctx.dispose();
      break;
    }
    case "bearer": {
      const b = A.bearer;
      if (b.storage === "header") meta.extraHTTPHeaders = { [b.headerName]: `${b.headerPrefix}${creds.token}` };
      else tokenStorage(b.storage, b.storageKey, creds.token, meta, origin);
      break;
    }
    case "cookie": {
      const c = A.cookie;
      const host = c.domain || new URL(config.web.baseUrl).hostname;
      const pairs = creds.cookie.includes("=")
        ? creds.cookie.split(";").map((p) => p.trim()).filter(Boolean).map((p) => [p.slice(0, p.indexOf("=")), p.slice(p.indexOf("=") + 1)])
        : [[c.name, creds.cookie]];
      const cookies = pairs.map(([name, value]) => ({
        name, value, domain: host, path: c.path, httpOnly: c.httpOnly, secure: c.secure, sameSite: c.sameSite, expires: -1,
      }));
      fs.writeFileSync(stateFile, JSON.stringify({ cookies, origins: [] }));
      meta.storageState = stateFile;
      break;
    }
    case "basic":
      meta.httpCredentials = { username: creds.username, password: creds.password };
      break;
    case "storage-state": {
      // Sessão gravada manualmente: npx playwright codegen --save-storage=arquivo.json <url>
      fs.copyFileSync(path.resolve(creds.storageStateFile), stateFile);
      meta.storageState = stateFile;
      break;
    }
    default:
      throw new Error(`Estratégia de login desconhecida: ${strategy}`);
  }
  fs.writeFileSync(sessionPath(role.name), JSON.stringify(meta, null, 2));
  return meta;
}

export function sessionMeta(role: string): SessionMeta | undefined {
  const file = sessionPath(role);
  return fs.existsSync(file) ? (JSON.parse(fs.readFileSync(file, "utf-8")) as SessionMeta) : undefined;
}

export function contextOptionsFor(role: string): BrowserContextOptions {
  if (role === "anonymous") return {};
  const meta = sessionMeta(role);
  if (!meta) throw new Error(`Sessão do papel '${role}' não foi criada (o setup de login falhou ou foi pulado).`);
  return {
    storageState: meta.storageState,
    extraHTTPHeaders: meta.extraHTTPHeaders,
    httpCredentials: meta.httpCredentials,
  };
}

/** Sai da conta pelo caminho configurado (auth.logout). */
export async function logout(page: Page): Promise<boolean> {
  const l = A.logout;
  if (l.method === "post" && l.path) {
    await page.request.post(url(l.path));
    return true;
  }
  if (l.selector) {
    await page.locator(l.selector).first().click();
    await page.waitForLoadState("networkidle").catch(() => undefined);
    return true;
  }
  if (l.path) {
    await page.goto(url(l.path));
    return true;
  }
  return false;
}
