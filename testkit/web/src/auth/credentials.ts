import { config, type RoleConfig } from "../config";

export interface Credentials {
  username: string;
  password: string;
  email: string;
  totpSecret: string;
  token: string;
  cookie: string;
  storageStateFile: string;
}

/** Credenciais vêm de variáveis <envPrefix>_USERNAME, _PASSWORD, _EMAIL, _TOTP_SECRET, _TOKEN, _COOKIE, _STORAGE_STATE. */
export function credentialsFor(role: RoleConfig): Credentials {
  const get = (suffix: string) => process.env[`${role.envPrefix}_${suffix}`] ?? "";
  const username = get("USERNAME");
  return {
    username,
    password: get("PASSWORD"),
    email: get("EMAIL") || username,
    totpSecret: get("TOTP_SECRET"),
    token: get("TOKEN"),
    cookie: get("COOKIE"),
    storageStateFile: get("STORAGE_STATE"),
  };
}

export function strategyFor(role: RoleConfig): string {
  return role.strategy || config.auth.strategy;
}

export function roles(): RoleConfig[] {
  return config.auth.strategy === "none" && !config.auth.roles.some((r) => r.strategy) ? [] : config.auth.roles;
}

export function roleByName(name: string): RoleConfig {
  const role = config.auth.roles.find((r) => r.name === name);
  if (!role) throw new Error(`Papel desconhecido: ${name}`);
  return role;
}

/** Substitui {{username}}, {{password}}, {{email}}, {{token}}, {{env.NOME}} em strings/objetos. */
export function template<T>(value: T, creds: Credentials, extra: Record<string, string> = {}): T {
  const map: Record<string, string> = { ...creds, ...extra } as unknown as Record<string, string>;
  const render = (s: string) =>
    s.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_, key: string) =>
      key.startsWith("env.") ? (process.env[key.slice(4)] ?? "") : (map[key] ?? ""),
    );
  const walk = (v: unknown): unknown => {
    if (typeof v === "string") return render(v);
    if (Array.isArray(v)) return v.map(walk);
    if (v && typeof v === "object") return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, walk(x)]));
    return v;
  };
  return walk(value) as T;
}

export function missingCredentials(role: RoleConfig): string[] {
  const c = credentialsFor(role);
  const s = strategyFor(role);
  const need: Record<string, (keyof Credentials)[]> = {
    form: ["username", "password"],
    "form-totp": ["username", "password", "totpSecret"],
    "form-email-code": ["username", "password", "email"],
    "magic-link": ["email"],
    oauth: ["username", "password"],
    api: [],
    bearer: ["token"],
    cookie: ["cookie"],
    basic: ["username", "password"],
    "storage-state": ["storageStateFile"],
    steps: [],
  };
  const suffix: Record<keyof Credentials, string> = {
    username: "USERNAME", password: "PASSWORD", email: "EMAIL", totpSecret: "TOTP_SECRET",
    token: "TOKEN", cookie: "COOKIE", storageStateFile: "STORAGE_STATE",
  };
  return (need[s] ?? []).filter((k) => !c[k]).map((k) => `${role.envPrefix}_${suffix[k]}`);
}
