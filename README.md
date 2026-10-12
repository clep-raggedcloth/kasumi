# 🌫 Kasumi — 家計報告書アプリ

クレジットカードの明細CSV（vpass等）をアップロードし、固定費と合算した月次の家計報告書をPDFで出力するWebアプリです。

## 機能

- **CSVアップロード** — Shift-JIS / UTF-8 を自動検出。複数カード・複数名義に対応
- **固定費管理** — 家賃・水道代など口座引き落としの固定費を登録・管理
- **現金払い** — 支払日ごとに登録・編集・削除し、その月のレポートに一度だけ計上
- **明細の除外** — レポートから除外したい明細をチェックボックスで選択
- **明細の補足・カテゴリ** — クレジットの購入内容を補足し、支払先ごとのカテゴリを次回取り込みに引き継ぎ
- **カテゴリ別支出** — クレジット・現金・固定費を合算した支出額と割合を円グラフで表示
- **月次レポート** — ブラウザで閲覧、カード名義別に明細を表示
- **PDF出力** — WeasyPrint + Noto フォントによる日本語対応PDF
- **拡張可能なパーサー** — vpass以外のカード会社にも対応できる設計

テスト: `uv run --with-requirements requirements-dev.txt python -m unittest discover -s tests -v`

## 対応カード会社

| カード会社 | 形式 |
|-----------|------|
| vpass（三井住友カード） | Shift-JIS CSV |

## 技術スタック

- **Backend**: FastAPI + SQLAlchemy + SQLite
- **Frontend**: Jinja2 + Tailwind CSS
- **PDF生成**: WeasyPrint
- **コンテナ**: Docker / docker-compose
