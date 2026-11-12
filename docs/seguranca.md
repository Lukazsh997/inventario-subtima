# Segurança

Revisão feita na Fase 6 (versão 1.0.0-rc.1). O sistema roda só na rede interna, mas foi revisado como se estivesse exposto, porque qualquer computador da rede alcança a porta.

## Controles existentes

| Área | Como está protegido |
|---|---|
| Autenticação | Senhas com Argon2; tamanho mínimo configurável; bloqueio temporário após `LOGIN_MAX_FAILURES` falhas (por usuário e por IP); mensagem de erro igual para usuário inexistente e senha errada; sessão expira por inatividade. |
| Autorização | Perfis (Administrador, Técnico de TI, Consulta) verificados **nos serviços**, não só nos botões. Teste automático: o perfil Consulta recebe 403 em todo POST do sistema; toda rota, exceto `/health/` e o login, exige login. |
| CSRF | Ativo em todos os formulários; cookies `SameSite=Lax`, `HttpOnly` na sessão, `Secure` com `USE_HTTPS=true`. |
| XSS | Templates com escape automático. Valores que vão para o JavaScript (Alpine) passam por `escapejs`; o tipo de operação vindo da URL é validado contra a lista de tipos. |
| Cabeçalhos | `Content-Security-Policy` (só recursos do próprio servidor; nenhum CDN), `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `Permissions-Policy` (só câmera, para o leitor), `Cross-Origin-Resource-Policy`. HSTS e redirecionamento HTTPS opcionais. |
| SQL | Apenas ORM e consultas parametrizadas. |
| Integridade | Histórico de operações, movimentos e auditoria protegido por gatilhos no PostgreSQL (UPDATE/DELETE recusados mesmo por acesso direto ao banco); saldo com `CHECK >= 0`; bloqueio de linha na movimentação. |
| PDF | WeasyPrint 70 com busca de recursos restrita a `data:`: um modelo de termo não consegue ler arquivos do servidor nem acessar a rede. Modelos usam um motor isolado que recebe só textos. |
| Uploads | Planilha de importação: só `.csv`/`.xlsx`, até 5 MB e 2.000 linhas, lida em memória e nunca gravada em disco. Imagens dos termos: só PNG/JPEG validados. |
| Container | Usuário sem privilégios (uid 1000), `tini` como init, banco sem porta publicada, segredos só por variável de ambiente. |
| Dependências | Versões fixadas por faixa em `requirements.txt`; `pip-audit` sem vulnerabilidades conhecidas na data da revisão. |

## O que foi encontrado e corrigido nesta revisão

1. **XSS refletido** pelo parâmetro `?tipo=` das telas de operação, que era inserido no `x-data` do Alpine sem escape de JavaScript. Corrigido (validação + `escapejs`) e coberto por teste.
2. **Listas que aceitavam POST** (usuários, setores, servidores) sem necessidade. Agora só GET.
3. **Sem Content-Security-Policy.** Adicionada; a política permite `unsafe-eval` porque o Alpine.js depende dele. Todos os scripts são servidos pelo próprio sistema.
4. **WeasyPrint 66** tinha falhas publicadas (leitura de arquivos/acesso à rede a partir do HTML e execução do Ghostscript por imagens EPS). Atualizado para a 70 e restringido a `data:`; teste garante que um PDF com `file://` e `http://` não carrega nada.

## Riscos aceitos e recomendações

- **HTTP sem criptografia na rede interna.** Recomendado colocar o proxy HTTPS (também necessário para a câmera do celular). Sem ele, a senha trafega em texto claro na rede.
- **`unsafe-eval` na CSP**, exigido pelo Alpine.js. O risco é baixo porque nenhum script externo é permitido.
- **Usuário inicial**: retire `ADMIN_INITIAL_PASSWORD` do `.env` depois do primeiro acesso.
- **Backups contêm todos os dados** (incluindo os termos). Guarde a pasta de backups com acesso restrito e copie para outro servidor.
- Rodar `pip-audit -r requirements.txt` a cada atualização de versão.
