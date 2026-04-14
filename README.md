# 🌫 Kasumi — 家計報告書アプリ

クレジットカードの明細CSV（vpass等）をアップロードし、固定費と合算した月次の家計報告書をPDFで出力するWebアプリです。

## 機能

- **CSVアップロード** — Shift-JIS / UTF-8 を自動検出。複数カード・複数名義に対応
- **固定費管理** — 家賃・水道代など口座引き落としの固定費を登録・管理
- **明細の除外** — レポートから除外したい明細をチェックボックスで選択
- **月次レポート** — ブラウザで閲覧、カード名義別に明細を表示
- **PDF出力** — WeasyPrint + Noto フォントによる日本語対応PDF
- **拡張可能なパーサー** — vpass以外のカード会社にも対応できる設計

## 対応カード会社

| カード会社 | 形式 |
|-----------|------|
| vpass（三井住友カード） | Shift-JIS CSV |

## 技術スタック

- **Backend**: FastAPI + SQLAlchemy + SQLite
- **Frontend**: Jinja2 + Tailwind CSS
- **PDF生成**: WeasyPrint
- **コンテナ**: Docker / docker-compose

## セットアップ

### 必要なもの

- Docker
- Docker Compose

### 起動

```bash
git clone https://github.com/clep-raggedcloth/kasumi.git
cd kasumi
docker compose up -d
```

ブラウザで http://localhost:8000 を開く。

### Synology NAS での運用

1. NAS に SSH でログイン
2. リポジトリをクローン
3. `docker compose up -d` で起動
4. `http://NAS-IP:8000` でアクセス

データは `./data/kasumi.db`（SQLite）に保存されます。Docker volume でホストにマウントされるためコンテナを削除してもデータは残ります。

## 使い方

### 1. 明細をアップロード

ホーム画面のアップロードゾーンにCSVをドラッグ＆ドロップ（またはクリックして選択）し、年・月を指定してアップロード。

### 2. 固定費を登録

「固定費」ページから家賃・光熱費・保険料など口座引き落としの費用を登録。有効/無効を切り替えできます。

### 3. レポートを確認

ホーム画面で年月を選択して「レポートを見る」。明細のチェックを外すと合計・PDFから除外されます。

### 4. PDF出力

レポート画面の「PDFダウンロード」ボタンから出力。

## 新しいカード会社への対応

`app/parsers/` に新ファイルを作成し `BaseParser` を継承するだけで追加できます。

```python
# app/parsers/mycard.py
from .base import BaseParser, ParsedStatement, register_parser

@register_parser
class MyCardParser(BaseParser):
    SOURCE_NAME = "mycard"

    @classmethod
    def can_parse(cls, content: str) -> bool:
        # このパーサーが処理できるCSVかを判定
        return "MyCard" in content[:200]

    @classmethod
    def parse(cls, content: str) -> ParsedStatement:
        # CSVを解析してParsdStatementを返す
        ...
```

作成したファイルを `app/routers/upload.py` で import すれば自動的に登録されます。

## ディレクトリ構成

```
kasumi/
├── app/
│   ├── main.py                  # FastAPI エントリーポイント
│   ├── models/database.py       # DB スキーマ
│   ├── parsers/
│   │   ├── base.py              # パーサー基底クラス・レジストリ
│   │   └── vpass.py             # vpass パーサー
│   ├── routers/
│   │   ├── upload.py            # CSV アップロード
│   │   ├── expenses.py          # 固定費 CRUD
│   │   └── reports.py           # レポート・PDF 出力
│   ├── templates/               # Jinja2 テンプレート
│   ├── static/
│   └── utils/pdf_generator.py
├── data/                        # SQLite（Docker volume）
├── uploads/                     # アップロードファイル（Docker volume）
├── Dockerfile
└── docker-compose.yml
```
