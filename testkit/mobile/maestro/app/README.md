# Fluxos próprios do app

Coloque aqui fluxos Maestro específicos do seu app (cadastro, compra, busca...).
Todos os arquivos `*.yaml` desta pasta rodam após o login.

Exemplo `navegacao-principal.yaml`:

```yaml
appId: ${APP_ID}
---
- launchApp
- tapOn:
    id: tab-busca
- inputText: "teste"
- assertVisible: "Resultados"
```

Gravar fluxos interativamente: `maestro studio`.
