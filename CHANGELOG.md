# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). Versões seguem [SemVer](https://semver.org/lang/pt-BR/).

## [0.4.0] - 2026-11-12

Fase 5 (termos e documentos).

### Adicionado
- Termos em PDF gerados automaticamente ao registrar a operação, com a opção "Gerar o termo em PDF ao registrar" marcada por padrão. O PDF fica guardado no banco de dados exatamente como foi emitido, com hash SHA-256 e os dados preenchidos.
- Reprodução fiel dos dois modelos institucionais recebidos: **Termo de Transferência** (transferência de equipamentos) e **Termo de Recebimento de Resmas** (saída de material). O texto é copiado literalmente; o brasão e o logotipo foram extraídos dos próprios arquivos.
- Número único do termo (`TR-AAAA-NNNNNN`), impresso discretamente no rodapé junto com o número da operação, para localizar a via assinada.
- Situações do termo: gerado, impresso (automática ao abrir para impressão), aguardando assinatura, assinado e recebido pela TI, arquivado e cancelado. O histórico registra quem mudou e quando.
- Reimpressão sempre do mesmo arquivo, com contador; reemissão (cancela o termo e gera outro com o modelo atual); cancelamento automático quando a operação é estornada.
- Modelos versionados e editáveis pelo administrador, com variáveis documentadas na tela, prévia com a operação real mais recente e "copiar layout" para criar modelos novos. Uma versão já usada nunca é alterada.
- Motor de modelos isolado: o modelo só recebe textos e números, sem acesso a objetos do banco, `{% load %}` ou `{% include %}`.
- Substituição do brasão e do logotipo por imagens de melhor resolução, pela interface.
- Página "Termos" com filtros (situação, pendentes de assinatura, modelo) e o relatório "Documentos e termos emitidos" (11º relatório).
- 15 testes novos (137 no total). Conferem o texto dos PDFs gerados contra os originais.

## [0.3.0] - 2026-11-12

Fase 4 (painel, alertas e relatórios).

### Adicionado
- Painel inicial com os 8 indicadores pedidos: equipamentos cadastrados, disponíveis, emprestados (com atrasados), em manutenção, unidades em estoque, movimentações no mês, estoque baixo e sem estoque.
- Seis gráficos (Chart.js local): entradas e saídas, consumo mensal, materiais mais retirados, equipamentos por setor, evolução do estoque e equipamentos por categoria. Cada um tem tabela equivalente ("Ver tabela").
- Filtros do painel por período, categoria e setor; atividades recentes.
- Alertas de estoque mínimo: registram quando a condição surge, atualizam o nível (baixo/zerado) sem duplicar, fecham ao normalizar e reabrem se voltar a faltar. Reagem a entradas, saídas, estornos, mudança de mínimo e desativação.
- Página "Materiais críticos" com consumo médio de 90 dias, duração estimada e sugestão de compra; histórico de alertas encerrados; contador no menu.
- 10 relatórios com filtros e exportação PDF (A4, cabeçalho, filtros aplicados e paginação) e CSV (Excel em português, proteção contra fórmulas): estoque atual, histórico de entradas, histórico de saídas, consumo mensal, abaixo do mínimo, equipamentos por setor, por responsável, emprestados, em manutenção e histórico individual.
- Reavaliação noturna dos alertas pelo agendador.
- 25 testes novos (122 no total), incluindo a conferência dos números do painel contra consultas diretas ao banco.

### Alterado
- Imagem Docker inclui as bibliotecas do WeasyPrint e as fontes Liberation, Carlito e Caladea (métricas de Arial, Calibri e Cambria) para os PDFs.

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
