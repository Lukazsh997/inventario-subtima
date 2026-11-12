# Estrutura do banco de dados

PostgreSQL 17. O esquema é versionado por migrações do Django (`src/apps/*/migrations`) e nunca é alterado manualmente.

## Tabelas (versão 0.4.0)

| Tabela | Conteúdo | Regras no banco |
|---|---|---|
| `accounts_user` | Usuários do sistema (equipe de TI): login, nome, hash Argon2 da senha, perfil (`admin`, `tecnico`, `consulta`), setor, ativo, contador de falhas de login, bloqueio temporário | Login único |
| `organization_sector` | Secretarias, subsecretarias, departamentos; `parent_id` forma a hierarquia | Nome único sem diferenciar maiúsculas; não pode ser pai de si mesmo; exclusão bloqueada se houver vínculos (`PROTECT`) |
| `organization_location` | Locais físicos (prédio, andar, sala) de um setor | Descrição única por setor |
| `organization_recipient` | Servidores que recebem materiais e assinam termos (sem login) | Matrícula única quando informada |
| `catalog_category` | Categorias, cada uma de um tipo: equipamento (controle individual) ou consumível (por quantidade) | Nome único por tipo |
| `catalog_equipment` | Equipamentos: dados cadastrais, propriedade (próprio/locado), locadora, nº de série, patrimônio, código da locadora (ACES), situação, setor/local/responsável atuais | Série, patrimônio (comparado pelos dígitos) e código da locadora únicos; pelo menos um dos três obrigatório |
| `catalog_consumable` | Materiais de consumo: nome, código do fabricante, unidade, estoque mínimo, compatibilidade | Nome e código únicos |
| `inventory_stockbalance` | Saldo atual de cada consumível | `CHECK (quantidade >= 0)`; alterado só sob bloqueio de linha |
| `inventory_stockoperation` | Operação: número `OP-AAAA-NNNNNN`, tipo, responsável, origem, destino, local, servidor recebedor, devolução prevista, assistência, justificativa, estorno de | **Imutável** (gatilhos rejeitam UPDATE/DELETE) |
| `inventory_stockmovement` | Linhas da operação: equipamento (quantidade 1) **ou** consumível (quantidade com sinal), saldo após, situação/setor/responsável antes | **Imutável**; exatamente um item por linha |
| `inventory_operationaccessory` | Acessórios entregues junto (carregador, bolsa…) | **Imutável** |
| `inventory_equipmentassignment` | Períodos de uso, empréstimo e manutenção de cada equipamento | No máximo uma atribuição aberta por equipamento |
| `alerts_lowstockalert` | Períodos em que um material ficou no mínimo ou abaixo: identificado em, saldo e mínimo naquele momento, nível atual, normalizado em, motivo | No máximo um alerta aberto por material (índice único parcial) |
| `documents_documenttemplate` | Modelos de termo: código, versão, nome, tipos de operação, CSS e HTML com variáveis, origem do texto | Uma versão ativa por modelo; versões usadas não mudam |
| `documents_documentasset` | Brasão e logotipo usados nos termos (imagem no banco) | Chave única |
| `documents_generateddocument` | Termos emitidos: número `TR-AAAA-NNNNNN`, operação, versão do modelo, **PDF (bytes)**, SHA-256, dados preenchidos, situação, impressões, substitui | Número único |
| `documents_documentstatuschange` | Histórico de situação de cada termo (de, para, quem, quando, observação) | — |
| `core_numbersequence` | Contador anual dos números de operação | Incremento atômico (`INSERT … ON CONFLICT`) |
| `audit_auditlog` | Auditoria: data, usuário, ação, entidade, resumo, alterações (JSON de/para), IP | **Somente inserção**: gatilhos rejeitam `UPDATE` e `DELETE` |

As tabelas `auth_*`, `django_*` e `django_session` são internas do framework.

## Princípios

- **Desativar em vez de apagar:** setores, locais, servidores e usuários com histórico são desativados. As chaves estrangeiras usam `PROTECT`.
- **Histórico imutável:** a função `patrimonio_forbid_change()` protege auditoria, operações, movimentações e acessórios. Correções são feitas por estorno, uma nova operação ligada à original.
- **Concorrência:** saídas bloqueiam as linhas de saldo e de equipamento (`SELECT … FOR UPDATE`, em ordem de id) até o fim da transação. Duas retiradas simultâneas do último item resultam em uma aprovada e uma recusada, o que é comprovado em teste com conexões paralelas.
- **Toda escrita passa pelos serviços** (`apps/*/services.py`), que validam permissão, regras e auditoria dentro de uma transação.

Os termos emitidos ficam no banco, então o backup diário (`pg_dump`) já os inclui.
