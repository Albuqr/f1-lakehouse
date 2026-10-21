# Testkit — suíte genérica de testes e verificações

Um kit único para aplicar em projetos **web (qualquer backend)**, **Python** e **mobile (Expo/React Native, Flutter, Android nativo, iOS)**, rodando localmente e no CI. A configuração fica em um arquivo JSON; as senhas e tokens ficam em variáveis de ambiente.

## O que é verificado

| Grupo | Verificações | Ferramenta |
|---|---|---|
| **Node/TS** | instalação, lint, formatação, tipos, testes, build (detecta npm/pnpm/yarn/bun e os scripts do projeto) | scripts do projeto, `tsc`, Prettier |
| **Python** | lint, formatação, tipos, testes com cobertura mínima, SAST, dependências vulneráveis, importação de todos os módulos | ruff, mypy, pytest + pytest-cov, bandit, pip-audit |
| **Segurança do código** | segredos vazados no histórico git, análise estática, dependências vulneráveis em todos os ecossistemas | gitleaks, semgrep, osv-scanner, npm/pnpm/yarn audit |
| **Navegador: fumaça** | cada página abre com status < 400, sem exceções JS, sem erros de console e sem requisições 5xx/falhas; página inexistente não gera 5xx | Playwright (Chromium, Firefox, WebKit) |
| **Navegador: login** | sessão por papel, senha errada recusada, sessão sobrevive a recarga, logout encerra a sessão, campo de senha protegido | Playwright |
| **Navegador: permissões** | matriz papel × página e papel × endpoint (permitido/bloqueado), incluindo visitante anônimo | Playwright |
| **Acessibilidade** | WCAG 2.0/2.1/2.2 A e AA + boas práticas, navegação por teclado, foco visível | axe-core |
| **Segurança HTTP** | cabeçalhos (CSP, nosniff, Referrer-Policy, clickjacking, HSTS), TRACE, arquivos sensíveis expostos (.env, .git...), vazamento de stack trace/SQL, CORS com credenciais, flags dos cookies de sessão, conteúdo misto | Playwright |
| **Responsividade** | sem rolagem horizontal em celular/tablet/desktop, meta viewport, alvos de toque mínimos | Playwright |
| **Performance** | TTFB, DOMContentLoaded, load, LCP, CLS, peso total e de JS com orçamentos; notas mínimas do Lighthouse | Playwright, Lighthouse CI |
| **Links** | varredura dos links internos (e externos, opcional) do site logado e deslogado; links da documentação Markdown | Playwright, lychee/linkinator |
| **API** | contrato OpenAPI e robustez (milhares de entradas geradas, respostas fora do schema, 5xx, métodos não suportados, autenticação) | Schemathesis |
| **Mobile** | análise estática (Flutter/Android/expo-doctor), app abre sem travar, login de todos os tipos, logout persistente, fluxos próprios | Maestro, emulador Android, simulador iOS |

Regressão visual por screenshot ficou de fora, como combinado.

## Instalação em um projeto

```bash
unzip testkit.zip
bash testkit/install.sh /caminho/do/projeto            # GitHub Actions (padrão)
bash testkit/install.sh /caminho/do/projeto --ci gitlab
```

O instalador:
- copia o kit para `<projeto>/testkit/`;
- cria um `testkit.config.json` inicial (se não existir);
- cria `.env.testkit.example`;
- coloca `.env.testkit` e `testkit-reports/` no `.gitignore`;
- instala `.github/workflows/testkit.yml`.

Para atualizar o kit depois, rode de novo com `--force`. A sua configuração na raiz não é alterada.

Requisitos: Python 3.10+ e bash. Node 18+ é necessário para os testes de navegador e projetos JS.

## Uso

```bash
bash testkit/bin/run-all.sh --validate     # confere a configuração
bash testkit/bin/run-all.sh --detect       # mostra o que será executado
bash testkit/bin/run-all.sh                # roda tudo que se aplica ao projeto
bash testkit/bin/run-all.sh web security   # só alguns grupos
```

Grupos disponíveis: `node python security links web lighthouse api mobile-static mobile-android mobile-ios`.

Cada grupo roda todas as etapas mesmo que uma falhe, e no fim mostra um resumo. O código de saída é diferente de zero se qualquer etapa falhar.

Comandos úteis para os testes de navegador:

```bash
cd testkit/web
npx playwright test --project=chromium          # um navegador só
npx playwright test auth authorization           # só alguns arquivos
npx playwright test --headed --project=chromium  # vendo o navegador
npx playwright test --ui                          # modo interativo
```

## Configuração

Tudo está em `testkit/defaults.json`. No `testkit.config.json` do projeto, declare **só o que muda**. Os arquivos de referência são:

- `testkit.config.example.json`: exemplo completo comentado;
- `examples/`: um arquivo pronto para cada tipo de login e de projeto.

Strings aceitam `${VARIAVEL}` e `${VARIAVEL:-padrão}`. Chaves que começam com `$` são comentários.

### Subir o app ou testar uma URL

- **App local**: use `web.baseUrl` com `localhost` mais `web.startCommand`. Opcionalmente, use também `web.setupCommand` para build ou migrações. O kit sobe o app, espera `readyPath` responder e o encerra no final.
- **Ambiente publicado** (staging/preview): defina `TESTKIT_BASE_URL`. Nesse caso nada é iniciado.

### Tipos de login (`auth.strategy`)

| Estratégia | Quando usar | Variáveis do papel |
|---|---|---|
| `none` | site sem login | — |
| `form` | usuário e senha (uma tela ou duas etapas com `form.twoStep`) | `_USERNAME`, `_PASSWORD` |
| `form-totp` | senha + código de app autenticador (MFA) | `_USERNAME`, `_PASSWORD`, `_TOTP_SECRET` |
| `form-email-code` | senha + código enviado por e-mail | `_USERNAME`, `_PASSWORD`, `_EMAIL` |
| `magic-link` | link mágico ou código por e-mail, sem senha (`magicLink.mode`) | `_EMAIL` |
| `oauth` | "Entrar com ..." via provedor OIDC/SAML/SSO | `_USERNAME`, `_PASSWORD` |
| `steps` | qualquer fluxo fora do padrão, descrito como uma lista de ações | o que os passos usarem |
| `api` | login por requisição (cookie, JWT em header/localStorage/sessionStorage, MFA por API) | `_USERNAME`, `_PASSWORD` (+ `_TOTP_SECRET`) |
| `bearer` | token fixo de integração/serviço | `_TOKEN` |
| `cookie` | cookie de sessão já emitido | `_COOKIE` |
| `basic` | HTTP Basic (staging protegido) | `_USERNAME`, `_PASSWORD` |
| `storage-state` | provedores que bloqueiam automação (Google, Apple, captcha): use uma sessão gravada | `_STORAGE_STATE` |

As variáveis seguem o padrão `<envPrefix>_<SUFIXO>`. Por exemplo, o papel `{ "name": "admin", "envPrefix": "TESTKIT_ADMIN" }` usa `TESTKIT_ADMIN_USERNAME`. Cada papel pode ter sua própria estratégia, então um mesmo projeto pode testar admin com MFA, usuário com link mágico e um bot com token.

Sobre MFA e e-mail:
- **TOTP**: o código é calculado a partir do segredo base32 (o mesmo do QR code). O kit espera uma janela nova para não reutilizar códigos, que muitos servidores recusam.
- **E-mail**: `auth.inbox` lê o Mailpit, o MailHog ou um endpoint próprio de teste (`type: "http"`, com `{{email}}` na URL).
- **Ações de `steps`**: `goto`, `fill`, `click`, `press`, `check`, `select`, `waitForUrl`, `waitForSelector`, `emailLink`, `fillEmailCode` e `wait`. Os valores aceitam `{{username}}`, `{{password}}`, `{{email}}`, `{{totp}}`, `{{token}}` e `{{env.NOME}}`.

### Papéis e permissões

```json
"roles": [
  { "name": "admin", "envPrefix": "TESTKIT_ADMIN", "homePath": "/admin" },
  { "name": "user",  "envPrefix": "TESTKIT_USER",  "homePath": "/app", "pages": ["/perfil"] }
],
"rules":    [{ "path": "/admin", "allow": ["admin"], "deny": ["user", "anonymous"] }],
"apiRules": [{ "method": "GET", "path": "/api/admin/users", "allow": ["admin"], "deny": ["user", "anonymous"] }]
```

As páginas de cada papel (`homePath`, `pages` e regras em que ele aparece em `allow`) passam por fumaça, acessibilidade, responsividade, performance e varredura de links, sempre logado como aquele papel. Visitantes anônimos usam `web.publicPages`.

### Ajustes frequentes

| Para | Configure |
|---|---|
| Ignorar um erro de console conhecido | `web.ignoreConsoleErrors` (regex) |
| Desligar um grupo de testes de navegador | `web.checks.<grupo>: false` |
| Mudar os navegadores | `web.browsers` |
| Ignorar uma regra de acessibilidade com justificativa | `web.accessibility.disableRules` |
| Ajustar os orçamentos de performance | `web.performance.budgets` e `web.performance.lighthouse.minScores` |
| Mudar a cobertura mínima do Python | `python.coverageMin` |
| Trocar um comando Node/Python | `node.commands.<etapa>` ou `python.commands.<etapa>` (`null` desativa a etapa) |
| Liberar falsos positivos de segredos | `security.allowlistFile` (arquivo `.gitleaks.toml`) |

## CI

### GitHub Actions

Workflow em `ci/github/testkit.yml`, com um job por grupo, rodando em paralelo:
1. Crie o segredo **`TESTKIT_ENV`** com o conteúdo do seu `.env.testkit`.
2. Opcional: crie a variável `TESTKIT_BASE_URL` para testar um ambiente publicado.
3. Opcional: crie a variável `TESTKIT_IOS=true` para ligar o job de iOS (runner macOS).
4. Se os testes precisarem de banco, descomente o bloco `services: postgres` no workflow.

Relatórios de cada job ficam em *Artifacts*, e os achados do semgrep aparecem na aba *Security*. Por padrão, o workflow usa as actions por versão (`@v4`). Para máxima segurança da cadeia de suprimentos, fixe cada uma pelo SHA do commit.

### GitLab CI

Use `include: - local: testkit/ci/gitlab/testkit.gitlab-ci.yml`, com uma variável do tipo *File* chamada `TESTKIT_ENV`. Mobile com emulador exige runner próprio com KVM.

O `run-all.sh` funciona em qualquer outro CI (Bitbucket, Azure, Jenkins): basta Python, Node e bash.

## Mobile

1. **Ids nos componentes**: os fluxos Maestro (`mobile/maestro/`) usam ids estáveis. Os padrões estão em `defaults.json` → `mobile.extraEnv` (`login-username`, `login-password`, `login-submit`, `home-screen`...). Coloque esses ids nos componentes (`testID` no React Native, `Semantics(identifier:)`/`Key` no Flutter, `resource-id` no Android, `accessibilityIdentifier` no iOS) ou mapeie para os seus em `mobile.extraEnv`.
2. **Build e app**: configure `mobile.appId`, `mobile.android.buildCommand` e `apkPath` (e o equivalente de iOS).
3. **Login**: o fluxo é escolhido por `auth.strategy` ou `mobile.authFlow`:
   - formulário;
   - TOTP (o código é gerado com pelo menos 20 s de validade);
   - link mágico (abre o deep link recebido por e-mail);
   - código por e-mail;
   - OAuth.
4. **Fluxos próprios**: coloque em `mobile/maestro/app/*.yaml`. Use `maestro studio` para gravar.

## Relatórios

Tudo vai para `testkit-reports/`:
- `summary.md`;
- `playwright-html/` (abra com `npx playwright show-report testkit-reports/playwright-html`), com trace, vídeo e screenshot das falhas;
- JUnit XML de todos os grupos;
- cobertura Python em XML;
- SARIF do gitleaks e do semgrep;
- relatórios do Lighthouse;
- log do servidor (`app-server.log`).

## Limitações conhecidas

- **Servidor de desenvolvimento**: os testes de segurança HTTP e performance são pensados para o build de produção. Rodar contra um servidor de desenvolvimento (Vite/webpack dev) acusa, como esperado, falta de cabeçalhos e JS pesado. Use `setupCommand` com build e `startCommand` com o servidor de produção, ou aponte `TESTKIT_BASE_URL` para staging.
- **Login social**: Google, Apple e Microsoft bloqueiam login automatizado. Use um provedor de teste ou `storage-state`.
- **Contrato da API**: o Schemathesis envia requisições reais, inclusive escrita. Rode só contra ambiente de teste. `DELETE` fica excluído por padrão.
- **iOS**: precisa de macOS (runner `macos-14`).
- **Varredura de links**: ignora links com `logout`, `sair`, `delete` e `excluir` para não alterar dados. Ajuste em `web.crawl.excludePatterns`.
- **Senha errada**: o teste de senha incorreta faz uma tentativa por papel. Se houver bloqueio de conta por tentativas, desligue com `auth.failure.checkInvalidLogin: false`.

## Estrutura

```
testkit/
├── install.sh                 instalador
├── defaults.json              todos os padrões
├── testkit.config.example.json
├── env.testkit.example
├── examples/                  configurações prontas por tipo de login/projeto
├── bin/
│   ├── run-all.sh             orquestrador
│   ├── checks/                node, python, security, links, web-e2e, lighthouse, api-contract, mobile
│   └── lib/                   config, TOTP, caixa de e-mail, token de API, servidor
├── web/                       suíte Playwright (TypeScript)
│   ├── src/auth/              motor de login (todas as estratégias)
│   └── tests/                 smoke, auth, authorization, a11y, security, responsive, performance, crawl
├── python/                    ferramentas, configs de referência e teste de importação
├── mobile/maestro/            fluxos Maestro (fumaça, login, logout, app/)
└── ci/                        GitHub Actions e GitLab CI
```
