import re
import unicodedata

from fastapi import HTTPException


CATEGORIES = (
    "食費", "日用品", "交通", "医療", "娯楽", "住居", "光熱費",
    "通信", "保険", "教育", "サブスク", "その他",
)
UNCATEGORIZED = "未分類"


def merchant_key(merchant: str) -> str:
    """同じ支払先の表記ゆれを限定的に吸収する。"""
    normalized = unicodedata.normalize("NFKC", merchant)
    return re.sub(r"\s+", " ", normalized.strip()).upper()


def validate_category(category: str, current: str | None = None, *, allow_uncategorized: bool = False) -> str | None:
    value = category.strip()
    if allow_uncategorized and value in ("", UNCATEGORIZED):
        return None
    if value in CATEGORIES or (current is not None and value == current):
        return value
    raise HTTPException(status_code=422, detail="カテゴリを選択してください")
