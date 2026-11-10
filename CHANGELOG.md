# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). Versões seguem [SemVer](https://semver.org/lang/pt-BR/).

## [0.1.0] - 2026-11-10

Fase 2 (fundação).

### Adicionado
- Estrutura do projeto em Django 5.2 LTS + PostgreSQL, configurada por variáveis de ambiente.
- Imagem Docker (usuário não-root, tini, cliente PostgreSQL 17) e `docker-compose.yml` compatível com Portainer Stacks, com os serviços `db`, `app` e `scheduler` e volumes persistentes.
- Endpoint `/health/` (banco e volume de dados) usado pelo `HEALTHCHECK`.
- Logs em JSON na saída padrão e em arquivo rotativo.
- Backup completo (banco + arquivos, com checksum) diário, antes de migrações e antes de restaurações; restauração com confirmação explícita.
- Login com hash Argon2, bloqueio temporário após falhas, sessão com expiração, proteção CSRF e contra redirecionamento aberto.
- Perfis Administrador, Técnico de TI e Consulta, com permissões verificadas nos serviços.
- Gestão de usuários: cadastro, edição, desativação, redefinição de senha. O sistema não permite ficar sem administrador ativo.
- Setores com hierarquia, locais físicos e servidores recebedores (sem login), com busca, filtros e paginação.
- Auditoria de todas as alterações e acessos, protegida no banco contra alteração e exclusão.
- Interface responsiva com menu lateral e confirmação de operações críticas.
- Documentação de implantação, backup/restauração, banco de dados e material de referência do órgão.
- 50 testes automatizados contra PostgreSQL.
