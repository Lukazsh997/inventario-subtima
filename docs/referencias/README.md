# Material de referência fornecido pelo órgão

Recebido em 10/11/2026. Usado nas próximas entregas; nada aqui é carregado automaticamente no sistema.

## Fluxo de trabalho desejado

- **Hoje:** o equipamento chega e é guardado sem inventário. Na saída, faz-se um termo de responsabilidade; a via assinada é copiada e arquivada em papel.
- **Com o sistema:** na chegada, o técnico lê o QR Code ou código de barras da etiqueta e o item entra no inventário. Na saída, o sistema dá baixa no inventário, gera o termo automaticamente e guarda o PDF no banco de dados.
- **LDAP:** o órgão tem LDAP, mas o sistema será usado só pela equipe de TI. A autenticação inicial é local; a integração continua prevista como opcional.

## Etiquetas (`etiquetas/`)

Conteúdo decodificado das fotos com o leitor ZXing, o mesmo usado pelo navegador:

| Foto | Etiqueta | Código de barras (Code 128) | QR Code |
|---|---|---|---|
| `patrimonio-prefeitura.jpg` | Patrimônio da Prefeitura | `085.057` (nº de patrimônio) | não tem |
| `locado-estabilizador.jpg` | "Patrimônio locado", impresso `ACES0000151` | `2419391010456` (nº de série) | `https://wa.me/552138991801?text= 2419391010456` |
| `locado-desktop-dell.jpg` | "Patrimônio locado", impresso `ACES0001123` | `8DBR9X1` (Service Tag Dell) | `https://wa.me/552138991801?text= ACES0001123` |
| `locado-impressora.jpg` | "Patrimônio locado", impresso `ACES0009234`, série `BRBST4S05J` | ilegível na foto | ilegível na foto |

Conclusões aplicadas no desenho (seção 7 da proposta):

- O sistema não gera etiquetas. Aceita a leitura de qualquer código das etiquetas existentes.
- O link do QR da locadora é normalizado: o valor depois de `text=` é usado na busca.
- Os campos pesquisáveis são número de série, patrimônio (comparado também só pelos dígitos) e código da locadora (ACES).
- O equipamento é marcado como próprio ou locado. A etiqueta da locadora pede contato prévio antes de movimentar o equipamento.

## Modelos de termo (`modelos-termos/`)

| Arquivo | Origem | Observações |
|---|---|---|
| `termo-de-transferencia.pdf` | Word 2024 | Tabela "Descrição – Estado de Conservação \| Marca/Modelo \| Patrimônio / Série", origem/setor/destino, duas assinaturas. A coluna Patrimônio/Série usa o nº de série no caso de itens locados. |
| `termo-de-recebimento-de-resmas.pdf` | Word + Acrobat | Frase "Eu ___, da Secretaria Municipal de … declaro ter recebido …"; rodapé com logotipo DC e endereço. |

**Ainda falta:** o modelo do **Termo de Responsabilidade** usado na saída de equipamento, além dos logotipos em boa resolução. O DOCX original seria útil, mas não é indispensável.

## Toners e suprimentos por impressora

Tabela fornecida pelo usuário (imagem). Será a carga inicial de consumíveis e de compatibilidade na Fase 3, depois de conferida pela equipe.

| Impressora | Toner / suprimento compatível |
|---|---|
| HP LaserJet Pro MFP M4103fdw | HP 151A (W1510A) / 151X (W1510X) |
| HP LaserJet Pro MFP M428fdw | HP 58A (CF258A) / 58X (CF258X) |
| HP Color LaserJet Pro MFP M479fdw | HP 414A / 414X – preto, ciano, magenta e amarelo |
| HP LaserJet Managed MFP E42540 | HP W9024MC – preto |
| Epson WorkForce Pro WF-C5890 | Epson T11A / T11B – preto, ciano, magenta e amarelo |
| Epson WorkForce Pro WF-M5899 | Epson T12B / T12C – preto |
| HP Color LaserJet Managed Flow E78635z | HP W9140MC a W9143MC / W9150MC a W9153MC – 4 cores |
| HP Color LaserJet Pro MFP 4303fdw | HP 230A / 230X – preto, ciano, magenta e amarelo |
| HP Color LaserJet Flow E77830 | HP W9190MC, W9191MC, W9192MC e W9193MC – 4 cores |
