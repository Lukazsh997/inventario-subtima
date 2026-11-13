# Patrimônio TI

Sistema web de gestão de patrimônio e estoque de TI: equipamentos identificados pelas etiquetas existentes, consumíveis controlados por quantidade, movimentações rastreáveis e termos de responsabilidade gerados automaticamente.

Desenvolvido para a Subsecretaria de Tecnologia da Informação e Modernização Administrativa (SUBTIMA) da Prefeitura Municipal de Duque de Caxias. Roda inteiramente na rede interna, em Docker, apenas com software livre.

## Situação atual: versão 0.3.0 (Fase 4: painel, alertas e relatórios)

| Módulo | Situação |
|---|---|
| Login, sessão segura, bloqueio após tentativas, troca de senha | pronto |
| Usuários do sistema e perfis (Administrador, Técnico de TI, Consulta) | pronto |
| Setores (hierarquia), locais físicos, servidores recebedores | pronto |
| Auditoria somente-inserção | pronto |
| Docker, health check, logs JSON, backup/restauração, agendador | pronto |
| Categorias, equipamentos (próprios e locados), materiais de consumo | pronto |
| Leitura das etiquetas existentes (câmera e leitor USB), busca global | pronto |
| Entradas, saídas, transferências, devoluções, empréstimos, manutenção, ajuste, baixa, estorno | pronto |
| Histórico imutável, saldo nunca negativo, histórico de localização/responsabilidade | pronto |
| Painel com indicadores, 6 gráficos e filtros por período, categoria e setor | pronto |
| Alertas de estoque mínimo (registro, sem duplicatas, encerramento automático) e página de materiais críticos | pronto |
| 10 relatórios com filtros e exportação em PDF (A4) e CSV | pronto |
| Termos em PDF a partir dos modelos institucionais | Fase 5 |

Guia de uso para a equipe: [docs/operacao.md](docs/operacao.md).

### Perfis

| Capacidade | Administrador | Técnico de TI | Consulta |
|---|:-:|:-:|:-:|
| Consultar setores, servidores, equipamentos, materiais e movimentações | ✓ | ✓ | ✓ |
| Cadastrar/editar servidores recebedores | ✓ | ✓ | |
| Entrada de equipamentos, cadastro de materiais | ✓ | ✓ | |
| Saídas, transferências, devoluções, empréstimos, manutenção, entradas de material | ✓ | ✓ | |
| Baixa de equipamento, ajuste de estoque, estorno | ✓ | | |
| Categorias, setores e locais | ✓ | | |
| Gerenciar usuários, consultar auditoria | ✓ | | |

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
| `APP_VERSION` / `APP_PORT` | | `0.3.0` / `8000` | Tag da imagem e porta publicada |
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

Monólito modular em Django 5.2 LTS com PostgreSQL 17, interface renderizada no servidor (Bootstrap 5, HTMX, Alpine.js, Chart.js, todos empacotados localmente, sem CDN) e PDFs gerados com WeasyPrint.

```
src/
├── config/            settings (via ambiente), urls, logging JSON
├── apps/
│   ├── core/          health check, listagem/paginação, agendador, componentes
│   ├── accounts/      usuários, perfis/RBAC, login com bloqueio
│   ├── organization/  setores, locais, servidores recebedores
│   ├── catalog/       categorias, equipamentos, materiais, leitura de etiquetas
│   ├── inventory/     operações, movimentações, saldos, atribuições, estorno
│   ├── alerts/        alertas de estoque mínimo (reagem a eventos de estoque)
│   ├── dashboard/     painel: indicadores e séries dos gráficos
│   ├── reports/       relatórios (tela, CSV e PDF a partir da mesma definição)
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
