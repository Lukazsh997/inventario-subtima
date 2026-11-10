# Estrutura do banco de dados

PostgreSQL 17. O esquema é versionado por migrações do Django (`src/apps/*/migrations`) e nunca é alterado manualmente.

## Tabelas da versão 0.1.0

| Tabela | Conteúdo | Regras no banco |
|---|---|---|
| `accounts_user` | Usuários do sistema (equipe de TI): login, nome, hash Argon2 da senha, perfil (`admin`, `tecnico`, `consulta`), setor, ativo, contador de falhas de login, bloqueio temporário | Login único |
| `organization_sector` | Secretarias, subsecretarias, departamentos; `parent_id` forma a hierarquia | Nome único sem diferenciar maiúsculas; não pode ser pai de si mesmo; exclusão bloqueada se houver vínculos (`PROTECT`) |
| `organization_location` | Locais físicos (prédio, andar, sala) de um setor | Descrição única por setor |
| `organization_recipient` | Servidores que recebem materiais e assinam termos (sem login) | Matrícula única quando informada |
| `audit_auditlog` | Auditoria: data, usuário, ação, entidade, resumo, alterações (JSON de/para), IP | **Somente inserção**: gatilhos rejeitam `UPDATE` e `DELETE` |

As tabelas `auth_*`, `django_*` e `django_session` são internas do framework.

## Princípios

- **Desativar em vez de apagar:** setores, locais, servidores e usuários com histórico são desativados. As chaves estrangeiras usam `PROTECT`.
- **Auditoria imutável:** a função `patrimonio_forbid_change()` também vai proteger as tabelas de movimentação na Fase 3.
- **Toda escrita passa pelos serviços** (`apps/*/services.py`), que validam permissão, regras e auditoria dentro de uma transação.

## Próximas tabelas

Categorias, equipamentos, consumíveis, saldos, operações e movimentações (Fase 3); alertas (Fase 4); modelos e termos gerados, com o PDF armazenado no próprio banco (Fase 5). O desenho completo está na proposta de arquitetura.
