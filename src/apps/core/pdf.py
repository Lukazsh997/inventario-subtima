"""Conversão HTML → PDF única para termos e relatórios.

O gerador só pode ler recursos embutidos no próprio HTML (data: URIs). Arquivos do
servidor (file://) e endereços de rede (http/https) são recusados, mesmo que um
modelo de termo editado os referencie: proteção contra leitura de arquivos e SSRF.
"""


def html_to_pdf(html: str) -> bytes:
    from weasyprint import HTML
    from weasyprint.urls import URLFetcher

    fetcher = URLFetcher(allowed_protocols={"data"}, allow_redirects=False, timeout=5)
    return HTML(string=html, url_fetcher=fetcher).write_pdf()
