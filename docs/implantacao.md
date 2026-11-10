# Implantação com Docker e Portainer

## Componentes

| Serviço | Imagem | Função | Volumes |
|---|---|---|---|
| `db` | `postgres:17-alpine` | Banco de dados. A porta não é exposta fora da stack. | `pgdata` |
| `app` | `patrimonio-ti:<versão>` (construída do `Dockerfile`) | Aplicação web (Gunicorn), porta 8000 | `appdata` → `/data`, backups → `/backups` |
| `scheduler` | mesma imagem do `app` | Backup diário no horário `BACKUP_TIME` | `appdata` (somente leitura), backups |

Os dados ficam todos em volumes nomeados. Recriar, atualizar ou reiniciar containers não apaga nada; só `docker compose down -v` remove os volumes.

## Primeira implantação

1. Copie o repositório para o servidor, ou aponte o Portainer para o repositório Git.
2. Crie o `.env` a partir de `.env.example`. As variáveis obrigatórias são `SECRET_KEY`, `DB_PASSWORD` e `ADMIN_INITIAL_PASSWORD`.
   - Para gerar a `SECRET_KEY`: `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`.
   - Em `ALLOWED_HOSTS`, liste o nome DNS e o IP pelos quais a equipe vai acessar o sistema.
3. Suba a stack com o build da imagem:
   ```sh
   docker compose up -d --build
   docker compose ps          # app deve ficar "healthy" em até 1 minuto
   curl http://localhost:8000/health/
   ```
4. Entre com `ADMIN_INITIAL_USER` / `ADMIN_INITIAL_PASSWORD`. Depois do primeiro acesso, troque a senha e retire `ADMIN_INITIAL_PASSWORD` do `.env`. O usuário inicial só é criado quando o banco não tem nenhum usuário.

### Portainer Stacks

- **Opção recomendada:** *Stacks → Add stack → Repository*, apontando para o repositório Git. O Portainer faz o build pelo `Dockerfile`. Informe as variáveis em *Environment variables* ou carregue o `.env`.
- **Alternativa:** faça o build da imagem no servidor (`docker build -t patrimonio-ti:0.1.0 .`) e cole o `docker-compose.yml` no *Web editor*. A seção `build` é ignorada quando a imagem já existe.

## HTTPS (necessário para a câmera do celular)

Os navegadores só liberam a câmera em HTTPS. Coloque um proxy reverso com o certificado do órgão na frente da porta 8000 e configure:

```
USE_HTTPS=true
CSRF_TRUSTED_ORIGINS=https://patrimonio.intranet.local
FORWARDED_ALLOW_IPS=<IP do proxy>
```

O proxy precisa repassar `X-Forwarded-Proto` e `X-Forwarded-For`. O leitor USB funciona mesmo sem HTTPS.

## Atualização de versão sem perda de dados

1. Altere `APP_VERSION` (ex.: `0.2.0`) e faça o build da nova imagem (Portainer: *Update the stack* com *Re-pull/rebuild*).
2. Ao iniciar, o `app` detecta migrações pendentes e **gera um backup `pre-migracao` antes de aplicá-las**. Se uma migração falhar, o container não sobe e o banco fica no estado anterior.
3. A versão em uso aparece no rodapé do menu e em `/health/`.

## Health check e logs

- `GET /health/` não exige login. Responde 200 quando o banco responde e o volume de dados aceita escrita; caso contrário, 503 com o detalhe. O `HEALTHCHECK` da imagem usa esse endpoint.
- Logs em JSON, uma linha por evento, na saída padrão (visíveis no Portainer). O `app` também grava em `/data/logs/app.log`, com rotação a cada 10 MB e 10 arquivos.
- A auditoria de negócio (quem fez o quê) fica no banco, no menu *Auditoria*.
