import { createHmac } from "node:crypto";
import { execFile } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { promisify } from "node:util";
import { AUTH_DIR, KIT_DIR } from "../config";

const run = promisify(execFile);
const BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

function base32Decode(input: string): Buffer {
  let secret = input;
  if (secret.startsWith("otpauth://")) secret = new URL(secret).searchParams.get("secret") ?? "";
  const clean = secret.replace(/[\s=-]/g, "").toUpperCase();
  let bits = 0;
  let value = 0;
  const out: number[] = [];
  for (const char of clean) {
    const idx = BASE32.indexOf(char);
    if (idx < 0) throw new Error("Segredo TOTP inválido (base32 esperado)");
    value = (value << 5) | idx;
    bits += 5;
    if (bits >= 8) {
      out.push((value >>> (bits - 8)) & 0xff);
      bits -= 8;
    }
  }
  return Buffer.from(out);
}

export function totpAt(secret: string, timeMs: number, digits = 6, period = 30): string {
  const counter = Math.floor(timeMs / 1000 / period);
  const buf = Buffer.alloc(8);
  buf.writeBigUInt64BE(BigInt(counter));
  const digest = createHmac("sha1", base32Decode(secret)).update(buf).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  const code = (digest.readUInt32BE(offset) & 0x7fffffff) % 10 ** digits;
  return String(code).padStart(digits, "0");
}

/**
 * Gera um código novo garantindo que (1) ele não expire nos próximos segundos e
 * (2) a mesma janela não seja reutilizada — muitos servidores rejeitam códigos repetidos.
 */
export async function freshTotp(secret: string, minRemainingSec = 8, period = 30): Promise<string> {
  fs.mkdirSync(AUTH_DIR, { recursive: true });
  const marker = path.join(AUTH_DIR, `.totp-${createHmac("sha256", "testkit").update(secret).digest("hex").slice(0, 12)}`);
  for (;;) {
    const now = Date.now();
    const step = Math.floor(now / 1000 / period);
    const remaining = period - ((now / 1000) % period);
    const lastUsed = fs.existsSync(marker) ? Number(fs.readFileSync(marker, "utf-8")) : -1;
    if (remaining >= minRemainingSec && step !== lastUsed) {
      fs.writeFileSync(marker, String(step));
      return totpAt(secret, now);
    }
    await new Promise((r) => setTimeout(r, (remaining + 0.5) * 1000));
  }
}

/** Busca link mágico ou código por e-mail (Mailpit, MailHog ou endpoint próprio). */
export async function fromInbox(kind: "link" | "code", recipient: string, sinceMs: number): Promise<string> {
  const python = process.env.PYTHON_BIN || "python3";
  const { stdout } = await run(python, [path.join(KIT_DIR, "bin", "lib", "inbox.py"), kind, recipient, "--since", String(sinceMs / 1000)], {
    env: process.env,
    timeout: 120_000,
  });
  const value = stdout.trim();
  if (!value) throw new Error(`Nenhum ${kind} recebido para ${recipient}`);
  return value;
}
