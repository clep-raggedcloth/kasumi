"""WeasyPrintを使ってHTMLからPDFを生成する"""

from weasyprint import HTML, CSS


def render_pdf(html_content: str) -> bytes:
    """HTML文字列をPDFバイト列に変換する"""
    doc = HTML(string=html_content)
    return doc.write_pdf()
