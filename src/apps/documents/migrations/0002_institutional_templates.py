"""Modelos institucionais reproduzidos dos arquivos fornecidos pela SUBTIMA em 10/11/2026
(docs/referencias/modelos-termos). O texto é o dos originais; só os campos variáveis
foram trocados por dados do sistema. Imagens extraídas dos próprios PDFs.
"""

from pathlib import Path

from django.db import migrations

ASSETS = Path(__file__).resolve().parent.parent / "assets"

HEADER_BOLD = """
<table class="cab"><tr>
  <td class="cab-img"><img src="{{ imagens.brasao }}" alt="Brasão de Duque de Caxias"></td>
  <td class="cab-txt">PREFEITURA MUNICIPAL DE DUQUE DE CAXIAS<br>SECRETARIA MUNICIPAL DE GOVERNO<br>
  SUBSECRETARIA&nbsp; DE TECNOLOGIA DA INFORMAÇÃO E MODERNIZAÇÃO ADMINISTRATIVA</td>
</tr></table>
"""

TRANSFER_CSS = """
@page { margin: 17mm 13mm 18mm 13mm; }
.cab { border-collapse: collapse; margin: 0 0 9mm 0; }
.cab-img { width: 19mm; vertical-align: top; padding: 0; }
.cab-img img { width: 17mm; }
.cab-txt { font-family: Arial, "Liberation Sans", sans-serif; font-weight: bold; font-size: 10.5pt; line-height: 1.15;
  vertical-align: top; padding: 0 0 0 2mm; }
.titulo { font-family: Calibri, Carlito, sans-serif; font-weight: bold; font-size: 12pt; text-align: center;
  margin: 0 0 6mm; }
.intro { font-family: Calibri, Carlito, sans-serif; font-size: 11pt; margin: 0 0 2mm; }
.bens { border-collapse: collapse; margin-left: 3mm; width: 97%; }
.bens th { font-family: "Times New Roman", "Liberation Serif", serif; font-weight: bold; font-size: 11pt;
  border: 0.6pt solid #000; padding: 0.6mm 2mm; text-align: center; }
.bens td { border: 0.6pt solid #000; padding: 3mm 2mm; vertical-align: middle; }
.bens td.desc { font-family: Calibri, Carlito, sans-serif; font-size: 10pt; width: 37%; }
.bens td.marca { font-family: Arial, "Liberation Sans", sans-serif; font-size: 12pt; text-align: center; width: 32%; }
.bens td.serie { font-family: Arial, "Liberation Sans", sans-serif; font-size: 12pt; text-align: center; }
.dados { font-family: Calibri, Carlito, sans-serif; font-size: 13pt; line-height: 1.55; margin: 42mm 0 0 0; }
.data { font-family: Calibri, Carlito, sans-serif; font-size: 13pt; text-align: center; margin: 14mm 0 0; }
.assinatura { font-family: "Times New Roman", "Liberation Serif", serif; font-size: 13pt; text-align: center;
  margin: 24mm 8mm 0; }
.assinatura .linha { border-top: 0.6pt solid #888; margin: 0 0 1mm; }
"""

TRANSFER_BODY = HEADER_BOLD + """
<p class="titulo">TERMO DE TRANSFERÊNCIA</p>
<p class="intro">Comunico a esta Subsecretaria a <b>TRANSFERÊNCIA</b> do(s) bem(s) permanente(s), abaixo relacionado:</p>
<table class="bens">
  <thead><tr><th>Descrição – Estado de Conservação</th><th>Marca/Modelo</th><th>Patrimônio / Série</th></tr></thead>
  <tbody>
  {% for item in itens %}
    <tr><td class="desc">{{ item.descricao|upper }} - {{ item.estado|upper }}</td>
        <td class="marca">{{ item.marca_modelo|upper }}</td><td class="serie">{{ item.patrimonio_serie }}</td></tr>
  {% endfor %}
  </tbody>
</table>
<div class="dados">
  Transferido da {{ origem.secretaria }}<br>
  Setor: {{ origem.rotulo }}<br>
  Para: {% if destino.sigla %}{{ destino.sigla }}{% else %}{{ destino.nome }}{% endif %}
</div>
<p class="data">{{ termo.cidade }}, {{ termo.data_extenso }}</p>
<div class="assinatura"><div class="linha"></div>Responsável pela transferência (nome legível e matrícula)</div>
<div class="assinatura"><div class="linha"></div>Agente recebedor (nome legível e matrícula)</div>
"""

RECEIPT_CSS = """
@page { margin: 15mm 23mm 18mm 30mm; }
.cab { border-collapse: collapse; margin: 0 0 14mm 0; }
.cab-img { width: 24mm; vertical-align: top; padding: 0; }
.cab-img img { width: 21mm; }
.cab-txt { font-family: Arial, "Liberation Sans", sans-serif; font-size: 12.5pt; line-height: 1.2;
  vertical-align: middle; padding: 0 0 0 1mm; }
.data { font-family: Arial, "Liberation Sans", sans-serif; font-size: 11pt; text-align: right; margin: 0 0 18mm; }
.titulo { font-family: Arial, "Liberation Sans", sans-serif; font-size: 13.5pt; text-align: center; margin: 0 0 30mm; }
.texto { font-family: Arial, "Liberation Sans", sans-serif; font-size: 11pt; line-height: 2.2; text-align: justify; }
.campo { font-weight: bold; }
.nome { display: inline-block; min-width: 105mm; border-bottom: 0.6pt solid #000; line-height: 1.2; }
.assinatura { font-family: "Times New Roman", "Liberation Serif", serif; font-size: 11.5pt; text-align: center;
  margin: 58mm auto 0; width: 70mm; letter-spacing: 0.2pt; }
.assinatura .linha { border-top: 0.6pt solid #000; margin: 0 0 3mm; }
.rodape { position: fixed; bottom: 0; left: 0; right: 0; }
.rodape table { width: 100%; border-collapse: collapse; }
.rodape .logo img { width: 52mm; }
.rodape .endereco { font-family: "Times New Roman", "Liberation Serif", serif; font-size: 9.5pt; text-align: right;
  line-height: 1.55; vertical-align: bottom; }
.rodape a { color: #0563c1; }
"""

RECEIPT_BODY = """
<table class="cab"><tr>
  <td class="cab-img"><img src="{{ imagens.brasao }}" alt="Brasão de Duque de Caxias"></td>
  <td class="cab-txt">PREFEITURA MUNICIPAL DE DUQUE DE CAXIAS<br>SECRETARIA MUNICIPAL DE GOVERNO<br>
  SUBSECRETARIA DE TECNOLOGIA DA INFORMAÇÃO E MODERNIZAÇÃO ADMINISTRATIVA</td>
</tr></table>
<p class="data">{{ termo.cidade }}, <span class="campo">{{ termo.dia }}</span> de <span class="campo">{{ termo.mes|capfirst }}</span> de {{ termo.ano }}.</p>
<p class="titulo">TERMO DE RECEBIMENTO DE RESMAS</p>
<p class="texto">Eu <span class="nome campo">{{ recebedor.nome }}{% if recebedor.matricula %} (mat. {{ recebedor.matricula }}){% endif %}</span>
da <span class="campo">{{ destino.secretaria }}</span> declaro ter recebido
<span class="campo">{% for item in itens %}{{ item.quantidade }} {{ item.unidade }} ({{ item.material }}){% if not forloop.last %}, {% endif %}{% endfor %}</span>.</p>
<div class="assinatura"><div class="linha"></div>Recebedor (Assinatura e Matrícula)</div>
<div class="rodape"><table><tr>
  <td class="logo"><img src="{{ imagens.logo_dc }}" alt="Prefeitura de Duque de Caxias"></td>
  <td class="endereco">Alameda Esmeralda, 206 - Jardim Primavera<br>CEP 25215260 - Duque de Caxias/RJ<br>
  CNPJ 29.138.328/0001-50 Tel: (21) 2773-6338<br><a href="https://www.duquedecaxias.rj.gov.br">www.duquedecaxias.rj.gov.br</a></td>
</tr></table></div>
"""

TEMPLATES = [
    {
        "code": "termo-transferencia", "name": "Termo de Transferência", "item_kind": "equipamento",
        "operation_types": ["transferencia"], "css": TRANSFER_CSS, "body": TRANSFER_BODY,
        "source": "Termo de Transferência entre a mesma Secretaria (PDF, Word 2024), recebido em 10/11/2026",
    },
    {
        "code": "termo-recebimento-resmas", "name": "Termo de Recebimento de Resmas", "item_kind": "consumivel",
        "operation_types": ["saida"], "css": RECEIPT_CSS, "body": RECEIPT_BODY,
        "source": "Cópia de Ofício Secretaria A4 (Termo de Recebimento de Resmas, PDF), recebido em 10/11/2026",
    },
]


def seed(apps, schema_editor):
    DocumentTemplate = apps.get_model("documents", "DocumentTemplate")
    DocumentAsset = apps.get_model("documents", "DocumentAsset")
    for key, name, filename in [("brasao", "Brasão de Duque de Caxias", "brasao.png"),
                                ("logo_dc", "Logotipo Prefeitura de Duque de Caxias", "logo-dc.png")]:
        if not DocumentAsset.objects.filter(key=key).exists():
            DocumentAsset.objects.create(key=key, name=name, content=(ASSETS / filename).read_bytes())
    for data in TEMPLATES:
        if not DocumentTemplate.objects.filter(code=data["code"]).exists():
            DocumentTemplate.objects.create(version=1, active=True, **data)


class Migration(migrations.Migration):
    dependencies = [("documents", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
