# Implantação com Docker e Portainer

## Componentes

| Serviço | Imagem | Função | Volumes |
|---|---|---|---|
| `db` | `postgres:17-alpine` | Banco de dados. A porta não é exposta fora da stack. | `pgdata` |
| `app` | `patrimonio-ti:<versão>` (construída do `Dockerfile`) | Aplicação web (Gunicorn), porta 8000 | `appdata` → `/data`, backups → `/backups` |
| `proxy` | `patrimonio-ti-proxy:<versão>` (Caddy, `docker/proxy`) | HTTPS nas portas 80/443 | `caddydata` (certificados), `certs` |
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
- **Alternativa:** faça o build da imagem no servidor (`docker build -t patrimonio-ti:1.0.0-rc.1 .`) e cole o `docker-compose.yml` no *Web editor*. A seção `build` é ignorada quando a imagem já existe.

## HTTPS (necessário para a câmera do celular)

Os navegadores só liberam a câmera em HTTPS. A stack já traz o serviço `proxy` (Caddy), que atende nas portas 80 e 443 e repassa para o `app`. Não há comando para rodar dentro dos containers: só variáveis.

```
SITE_ADDRESS=patrimonio.intranet.local, 10.0.0.10   # nomes/IPs digitados no navegador
ALLOWED_HOSTS=patrimonio.intranet.local,10.0.0.10   # os mesmos
USE_HTTPS=true
TLS_CERT=internal
DEFAULT_SNI=10.0.0.10                               # IP do servidor (acesso por https://IP)
APP_BIND=127.0.0.1                                  # fecha a porta 8000 para a rede
```

Depois, recrie a stack (Portainer: *Update the stack* com *Re-pull/rebuild*; terminal: `docker compose up -d --build`). Acesse `https://patrimonio.intranet.local`. Quem entrar por `http://` é redirecionado.

**Certificado.** Há duas opções:
- `TLS_CERT=internal` (padrão): o próprio Caddy cria uma autoridade certificadora interna e emite o certificado. Para o navegador confiar, instale uma vez o certificado raiz em cada computador e celular. O arquivo fica disponível em `http://<servidor>/certificado-ca.crt`.
  - Windows: abrir o arquivo → *Instalar certificado* → *Máquina local* → *Autoridades de Certificação Raiz Confiáveis*. Em rede com domínio, dá para distribuir por GPO.
  - Android: *Configurações → Segurança → Criptografia e credenciais → Instalar certificado → Certificado de CA*.
  - iPhone: abrir o arquivo, instalar o perfil e ativar em *Ajustes → Geral → Sobre → Ajustes de Confiança de Certificados*.
- Certificado do órgão: coloque `cert.pem` (certificado + cadeia) e `key.pem` numa pasta do servidor e configure `CERTS_PATH=/caminho/da/pasta` e `TLS_CERT=/certs/cert.pem /certs/key.pem`.

**Se não abrir:**

| Sintoma | Verificar |
|---|---|
| `ERR_CONNECTION_REFUSED` | O container `proxy` está rodando? (`docker compose ps`; logs do `proxy`). Outra aplicação já usa a porta 80/443 no servidor? Use `HTTP_PORT`/`HTTPS_PORT` para trocar. Firewall do servidor liberando 80 e 443. |
| `ERR_SSL_PROTOCOL_ERROR` ou conexão encerrada ao abrir pelo IP | `DEFAULT_SNI` deve ser o IP do servidor. |
| HTTP também não abre | Normal com `APP_BIND=127.0.0.1`: a porta 8000 fica fechada e o `http://` manda para o HTTPS. Para voltar temporariamente ao HTTP: `APP_BIND=0.0.0.0` e `USE_HTTPS=false`, e acesse `http://<servidor>:8000`. |
| Bad Request (400) | O nome digitado não está em `ALLOWED_HOSTS`. |
| Aviso de certificado | Certificado raiz não instalado naquele aparelho, ou o nome digitado não está em `SITE_ADDRESS`. |
| 502 | O `app` não está saudável (logs do `app`). |

Se o órgão já tiver outro proxy reverso, remova o serviço `proxy` da stack, aponte o proxy existente para `http://<servidor>:8000` (repassando `Host`, `X-Forwarded-Proto` e `X-Forwarded-For`) e mantenha `APP_BIND=0.0.0.0`.

Opcional, depois que tudo funcionar em todas as máquinas: `SECURE_SSL_REDIRECT=true` e `SECURE_HSTS_SECONDS=31536000` (o HSTS é difícil de desfazer; deixe por último).

## Atualização de versão sem perda de dados

1. Altere `APP_VERSION` (ex.: `0.2.0`) e faça o build da nova imagem (Portainer: *Update the stack* com *Re-pull/rebuild*).
2. Ao iniciar, o `app` detecta migrações pendentes e **gera um backup `pre-migracao` antes de aplicá-las**. Se uma migração falhar, o container não sobe e o banco fica no estado anterior.
3. A versão em uso aparece no rodapé do menu e em `/health/`.

## Health check e logs

- `GET /health/` não exige login. Responde 200 quando o banco responde e o volume de dados aceita escrita; caso contrário, 503 com o detalhe. O `HEALTHCHECK` da imagem usa esse endpoint.
- Logs em JSON, uma linha por evento, na saída padrão (visíveis no Portainer). O `app` também grava em `/data/logs/app.log`, com rotação a cada 10 MB e 10 arquivos.
- `python manage.py verificar_implantacao` (dentro do container `app`) confere configuração, migrações, gatilhos do histórico, volumes, último backup, modelos de termo e geração de PDF. Veja [homologacao.md](homologacao.md).
- A auditoria de negócio (quem fez o quê) fica no banco, no menu *Auditoria*.
