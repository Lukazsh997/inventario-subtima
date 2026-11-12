# Guia de operação para a equipe de TI

## Leitura de etiquetas

O sistema usa as etiquetas que já existem nos equipamentos e não imprime etiquetas próprias.

| Etiqueta | O que ler |
|---|---|
| Patrimônio da Prefeitura | O código de barras (ex.: `085.057`). Também pode ser digitado com ou sem ponto. |
| "Patrimônio locado" | O código de barras (nº de série), o QR Code (contém o código ACES ou a série) ou o código `ACES…` digitado |

- **Leitor USB:** clique no campo e leia. O leitor precisa ser **2D** para ler QR Code; leitores a laser 1D só leem o código de barras.
- **Câmera do celular:** botão com o ícone de câmera ao lado do campo. Só funciona com o sistema acessado por HTTPS.
- **Busca global**, no topo de todas as páginas: lendo ou digitando um código, a ficha do equipamento abre direto.

## Chegou um equipamento (entrada)

1. Menu **Equipamentos → Entrada de equipamento**, ou botão na tela inicial.
2. Leia a etiqueta no campo correspondente. Preencha categoria, nome, fabricante e modelo. Para equipamento locado, informe a locadora.
3. **Inventário inicial:** se o equipamento já está em uso em um setor, marque *"já está em uso em um setor"* e informe o setor e o servidor. Se o servidor não estiver cadastrado, use *"+ Servidor não está na lista"* e cadastre na hora.
4. Para vários equipamentos iguais, use **Salvar e cadastrar outro igual**: categoria, fabricante e modelo são repetidos.

O sistema recusa identificadores repetidos e mostra qual equipamento já usa aquele código.

## Entregar, transferir, devolver, emprestar, mandar para manutenção

1. **Movimentar equipamento**, ou o botão da ação na ficha do equipamento.
2. Escolha o tipo e **bipe as etiquetas em sequência**. Uma operação pode ter vários equipamentos e gera um único termo.
3. Informe o setor de destino e o servidor que recebe. Na entrega de notebook, inclua os acessórios (carregador, bolsa, mouse).
4. **Registrar.** O sistema confere a situação de cada item; por exemplo, não é possível entregar um equipamento que já está em uso. A operação recebe um número (`OP-2026-000123`).

| Tipo | Situação exigida | Situação depois |
|---|---|---|
| Saída (entrega) | Disponível | Em uso |
| Transferência entre setores | Em uso | Em uso (novo setor/responsável) |
| Devolução | Em uso | Disponível |
| Empréstimo temporário | Disponível | Emprestado (com data prevista de devolução) |
| Retorno de empréstimo | Emprestado | Disponível |
| Envio para manutenção | Disponível ou em uso | Em manutenção |
| Retorno de manutenção | Em manutenção | Disponível |
| Baixa (só administrador) | Disponível, em uso ou em manutenção | Baixado (definitivo) |

Equipamento **locado** mostra um aviso, porque a etiqueta da locadora pede contato prévio antes de movimentá-lo.

## Materiais de consumo (toner, papel, cabos…)

- **Entrada:** *Materiais de consumo → Entrada*. Informe a quantidade recebida e, se quiser, a nota fiscal ou o empenho.
- **Retirada:** *Retirada de material*. Escolha o material (o saldo aparece ao lado), a quantidade, o setor e o servidor. A tela mostra quanto vai sobrar, e o sistema **não permite estoque negativo**.
- **Devolução:** material que voltou lacrado. Informe o setor que devolveu.
- **Ajuste (só administrador):** correção após inventário físico, com justificativa obrigatória.
- A lista destaca em amarelo o que está **no mínimo ou abaixo** e em vermelho o que está **sem estoque**.

A tabela de toners e tintas das impressoras do órgão pode ser carregada uma vez pelo administrador:

```sh
docker compose exec app /app/docker/entrypoint.sh manage carregar_suprimentos --usuario admin --simular
docker compose exec app /app/docker/entrypoint.sh manage carregar_suprimentos --usuario admin
```

O comando cria 43 materiais com saldo 0 e mínimo 0. Depois, registre as entradas e ajuste os mínimos de cada um.

## Errei uma operação: estorno

Nenhuma operação é apagada ou editada. Para corrigir, o **administrador** abre a operação e usa **Estornar**, com justificativa. O sistema cria uma operação inversa ligada à original e as duas ficam no histórico.

- Em equipamentos, só a operação mais recente de cada item pode ser estornada. Para desfazer uma anterior, estorne primeiro as posteriores.
- A **entrada** de um equipamento não é estornada. Dado cadastral errado se corrige em **Corrigir cadastro**; equipamento cadastrado por engano recebe **baixa**.
- Um estorno nunca deixa saldo negativo.
- Dados cadastrais (nome, modelo, série, patrimônio…) podem ser corrigidos a qualquer momento em **Corrigir cadastro**, e cada alteração fica na auditoria. Situação, setor e responsável mudam somente por movimentação.

## Painel, alertas e relatórios

- **Painel:** é a tela inicial. Mostra os indicadores e os gráficos do período escolhido (padrão: últimos 12 meses). Os filtros de categoria e setor valem para os indicadores e os gráficos em que fazem sentido. Cada indicador leva à lista correspondente, e cada gráfico tem **Ver tabela** com os números exatos.
- **Materiais críticos:** um material entra em alerta quando o saldo **atinge ou fica abaixo do estoque mínimo**. Só materiais com mínimo maior que zero geram alerta, então configure o mínimo em *Materiais de consumo → Editar*. O alerta registra quando a condição foi identificada e fecha sozinho quando o saldo volta acima do mínimo. O número ao lado do menu mostra quantos estão abertos. A sugestão de compra cobre a volta ao mínimo mais 3 meses do consumo médio recente.
- **"Materiais sem estoque"** no painel conta todos os materiais ativos com saldo 0, inclusive os que nunca tiveram entrada.
- **Relatórios:** escolha o relatório, aplique os filtros e use **PDF** (A4, para imprimir ou arquivar) ou **CSV** (abre direto no Excel ou no LibreOffice). O relatório *Histórico individual de equipamento* aceita a leitura da etiqueta no campo de busca.

## Termos

1. Ao registrar uma saída, transferência etc., deixe marcado **"Gerar o termo em PDF ao registrar"**. A operação abre com o termo pronto; clique em **Imprimir**.
2. Entregue o termo impresso ao requisitante, que confere e assina. A TI guarda a via assinada.
3. No termo (menu **Termos** ou pela operação), atualize a situação: *Aguardando assinatura → Assinado e recebido pela TI → Arquivado*. O filtro **Pendentes** lista o que ainda não voltou assinado.
4. **Reimprimir** sempre gera o mesmo PDF emitido. **Reemitir** cancela o termo e gera outro número, por exemplo depois de atualizar o modelo.
5. Se a operação for estornada, o termo é cancelado automaticamente.

O número do termo e o da operação saem em letra pequena no rodapé, para localizar no sistema a via em papel.

**Qual secretaria aparece no termo:** a mais próxima do setor de destino (ou de origem), ou seja, o primeiro nível da hierarquia de setores cujo nome começa com "Secretaria". Por isso, cadastre os departamentos *dentro* da secretaria a que pertencem. Se não houver secretaria acima, o termo mostra o nível logo abaixo da Prefeitura ou o próprio setor.

### Modelos de termo (administrador)

- Disponíveis hoje: **Termo de Transferência** (transferência de equipamentos) e **Termo de Recebimento de Resmas** (saída de materiais), reproduzidos dos arquivos do órgão.
- **Saída, empréstimo e devolução de equipamento** ainda não têm modelo, porque o Termo de Responsabilidade oficial ainda não foi fornecido. Essas operações funcionam normalmente; só não geram PDF. Quando o modelo chegar, cadastre-o em *Termos → Modelos de termo → Novo modelo* (ou use **Copiar layout** do Termo de Transferência) e informe a origem do texto.
- Editar um modelo cria uma nova versão. Os termos antigos continuam com a versão com que foram emitidos.
- Brasão e logotipo podem ser trocados por arquivos de melhor resolução em *Modelos de termo → Imagens*.
