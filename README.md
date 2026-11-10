# Patrimônio TI

Sistema web de gestão de patrimônio e estoque de TI: equipamentos identificados pelas etiquetas existentes, consumíveis controlados por quantidade, movimentações rastreáveis e termos de responsabilidade gerados automaticamente.

Desenvolvido para a Subsecretaria de Tecnologia da Informação e Modernização Administrativa (SUBTIMA) da Prefeitura Municipal de Duque de Caxias. Roda inteiramente na rede interna, em Docker, apenas com software livre.

## Situação atual: versão 0.1.0 (Fase 2: fundação)

| Módulo | Situação |
|---|---|
| Login, sessão segura, bloqueio após tentativas, troca de senha | pronto |
| Usuários do sistema e perfis (Administrador, Técnico de TI, Consulta) | pronto |
| Setores (hierarquia), locais físicos, servidores recebedores | pronto |
| Auditoria somente-inserção | pronto |
| Docker, health check, logs JSON, backup/restauração, agendador | pronto |
| Equipamentos, consumíveis, leitura de etiquetas, movimentações | Fase 3 |
| Dashboard, alertas de estoque mínimo, relatórios | Fase 4 |
| Termos em PDF a partir dos modelos institucionais | Fase 5 |

### Perfis

| Capacidade | Administrador | Técnico de TI | Consulta |
|---|:-:|:-:|:-:|
| Consultar setores e servidores | ✓ | ✓ | ✓ |
| Cadastrar/editar servidores recebedores | ✓ | ✓ | |
| Cadastrar/editar setores e locais | ✓ | | |
| Gerenciar usuários | ✓ | | |
| Consultar auditoria | ✓ | | |

As permissões são verificadas nos serviços, e não apenas na interface. O mapa fica em `src/apps/accounts/permissions.py`.

## Implantação rápida

```sh
cp .env.example .env      # preencha SECRET_KEY, DB_PASSWORD, ADMIN_INITIAL_PASSWORD, ALLOWED_HOSTS
docker compose up -d --build
curl http://localhost:8000/health/
```

Detalhes, Portainer, HTTPS e atualização: [docs/implantacao.md](docs/implantacao.md).
Backup e restauração: [docs/backup-e-restauracao.md](docs/backup-e-restauracao.md).
Banco de dados: [docs/banco-de-dados.md](docs/banco-de-dados.md).
Material recebido do órgão (etiquetas, modelos de termo, toners): [docs/referencias/](docs/referencias/README.md).

## Variáveis de ambiente

| Variável | Obrigatória | Padrão | Descrição |
|---|:-:|---|---|
| `SECRET_KEY` | sim | — | Chave criptográfica do Django (longa e aleatória) |
| `DB_PASSWORD` | sim | — | Senha do banco |
| `DB_NAME` / `DB_USER` | | `patrimonio` | Nome do banco e usuário |
| `ALLOWED_HOSTS` | | `localhost` | Nomes/IPs de acesso, separados por vírgula |
| `CSRF_TRUSTED_ORIGINS` | com HTTPS | — | Ex.: `https://patrimonio.intranet.local` |
| `USE_HTTPS` | | `false` | `true` atrás de proxy HTTPS (cookies seguros) |
| `FORWARDED_ALLOW_IPS` | com proxy | `127.0.0.1` | IP do proxy reverso confiável |
| `APP_VERSION` / `APP_PORT` | | `0.1.0` / `8000` | Tag da imagem e porta publicada |
| `ORG_NAME` / `ORG_UNIT_NAME` | | genéricos | Nome do órgão e da unidade (tela e documentos) |
| `TIME_ZONE` | | `America/Sao_Paulo` | Fuso horário |
| `SESSION_TIMEOUT_MINUTES` | | `480` | Sessão expira após inatividade |
| `LOGIN_MAX_FAILURES` / `LOGIN_LOCK_MINUTES` | | `5` / `15` | Bloqueio temporário após falhas de login |
| `PASSWORD_MIN_LENGTH` | | `10` | Tamanho mínimo de senha |
| `ADMIN_INITIAL_USER` / `ADMIN_INITIAL_PASSWORD` / `ADMIN_INITIAL_NAME` | 1ª subida | `admin` | Administrador criado se o banco estiver vazio |
| `BACKUP_TIME` / `BACKUP_RETENTION_DAYS` / `BACKUP_PATH` | | `02:00` / `30` / volume | Backup diário |
| `LOG_LEVEL` | | `INFO` | Nível de log |
| `GUNICORN_WORKERS` | | `3` | Processos da aplicação |

## Arquitetura

Monólito modular em Django 5.2 LTS com PostgreSQL 17, interface renderizada no servidor (Bootstrap 5, HTMX, Alpine.js, todos empacotados localmente, sem CDN).

```
src/
├── config/            settings (via ambiente), urls, logging JSON
├── apps/
│   ├── core/          health check, listagem/paginação, agendador, componentes
│   ├── accounts/      usuários, perfis/RBAC, login com bloqueio
│   ├── organization/  setores, locais, servidores recebedores
│   └── audit/         auditoria somente-inserção
├── templates/         layout base e componentes reutilizáveis
└── static/            CSS/JS do sistema e bibliotecas locais
```

Cada app separa `models.py` (entidades e restrições), `services.py` (casos de uso transacionais, permissão e auditoria), `forms.py` (validação de entrada) e `views.py` (finas: chamam o serviço e renderizam).

## Desenvolvimento

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
export DEBUG=true DB_PASSWORD=...           # PostgreSQL local
cd src && python manage.py migrate && python manage.py runserver
cd .. && pytest                             # testes contra PostgreSQL real
ruff check . && ruff format --check src tests
```
