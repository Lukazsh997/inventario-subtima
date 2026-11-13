# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). Versões seguem [SemVer](https://semver.org/lang/pt-BR/).

## [0.2.0] - 2026-11-12

Fase 3 (estoque).

### Adicionado
- Categorias de equipamento e de consumo, com as categorias iniciais do documento de requisitos e "Estabilizadores".
- Equipamentos próprios e locados, identificados pelas etiquetas existentes: patrimônio da Prefeitura, nº de série e código ACES da locadora. O link do QR da locadora é convertido no código.
- Leitura pela câmera (html5-qrcode/ZXing, local) e por leitor USB; tela "Ler etiqueta" e busca global que abre direto a ficha.
- Entrada de equipamento, inclusive "já em uso" para o inventário inicial e "salvar e cadastrar outro igual".
- Operações de equipamento: saída, transferência, devolução, empréstimo (com data prevista), retorno, envio e retorno de manutenção, baixa. Vários itens por operação, acessórios entregues e cadastro rápido de servidor.
- Materiais de consumo com saldo: entrada, saída, devolução e ajuste. Estoque negativo bloqueado no serviço e no banco.
- Estorno de operações com justificativa, mantendo a original.
- Histórico imutável (gatilhos no banco), numeração `OP-AAAA-NNNNNN` e histórico de localização e responsabilidade por equipamento.
- Tela inicial com totais por situação e materiais críticos ou sem estoque.
- Comando `carregar_suprimentos` com os 43 toners e tintas informados pela equipe.
- Guia de operação (`docs/operacao.md`).
- 47 testes novos (97 no total), incluindo retiradas simultâneas com conexões paralelas reais.

### Alterado
- Perfis Técnico de TI e Consulta passam a acessar o estoque; baixa, ajuste e estorno são exclusivos do Administrador.

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
