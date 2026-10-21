import { test as setup } from "@playwright/test";
import { missingCredentials, roles } from "../../src/auth/credentials";
import { establishSession } from "../../src/auth/login";

// Cria uma sessão por papel e salva em testkit-reports/.auth para todos os testes reutilizarem.
setup.describe.configure({ mode: "serial" });

for (const role of roles()) {
  setup(`login: ${role.name}`, async ({ browser }) => {
    const missing = missingCredentials(role);
    if (missing.length) {
      throw new Error(`Defina as variáveis ${missing.join(", ")} (em .env.testkit ou nos segredos do CI) para o papel '${role.name}'.`);
    }
    await establishSession(browser, role);
  });
}

setup("configuração carregada", async () => {
  // Garante que o projeto "setup" sempre tenha ao menos um teste, mesmo sem login.
});
