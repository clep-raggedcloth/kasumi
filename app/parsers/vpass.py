"""
vpass（三井住友カード）CSV パーサー

CSV構造:
  ヘッダー行: 名前,カード番号,カード名
  データ行:   日付,店舗名,金額,分割回数,??,請求額,備考
  小計行:     ,,,,,小計金額
  複数カードセクションが連続する場合あり
"""

import csv
import io
from datetime import date, datetime
from typing import Optional

from .base import BaseParser, ParsedStatement, ParsedTransaction, register_parser


def _is_header_row(row: list[str]) -> bool:
    """名前を含むセクションヘッダー行を判定する"""
    return len(row) >= 3 and "様" in row[0] and row[1].startswith(("4", "5", "6", "3"))


def _is_subtotal_row(row: list[str]) -> bool:
    """小計行（日付空、金額あり）を判定する"""
    return len(row) >= 6 and row[0] == "" and row[5].lstrip("-").isdigit()


def _parse_amount(s: str) -> Optional[int]:
    s = s.strip().replace(",", "")
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


@register_parser
class VpassParser(BaseParser):
    SOURCE_NAME = "vpass"

    @classmethod
    def can_parse(cls, content: str) -> bool:
        return "様," in content[:500] or "様," in content[:500]

    @classmethod
    def parse(cls, content: str) -> ParsedStatement:
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)

        transactions: list[ParsedTransaction] = []
        current_holder: Optional[str] = None
        current_card_number: Optional[str] = None
        current_card_name: Optional[str] = None

        for row in rows:
            # 短すぎる行はスキップ
            if len(row) < 2:
                continue

            # セクションヘッダー行
            if _is_header_row(row):
                current_holder = row[0].replace("様", "").strip()
                current_card_number = row[1].strip() if len(row) > 1 else None
                current_card_name = row[2].strip() if len(row) > 2 else None
                continue

            # 小計・合計行はスキップ
            if _is_subtotal_row(row):
                continue

            # データ行: 先頭が日付形式
            date_str = row[0].strip()
            if not date_str:
                continue
            try:
                txn_date = datetime.strptime(date_str, "%Y/%m/%d").date()
            except ValueError:
                continue

            merchant = row[1].strip() if len(row) > 1 else ""
            amount = _parse_amount(row[5]) if len(row) > 5 else None
            if amount is None:
                amount = _parse_amount(row[2]) if len(row) > 2 else 0
            memo = row[6].strip() if len(row) > 6 else None

            transactions.append(ParsedTransaction(
                date=txn_date,
                merchant=merchant,
                amount=amount or 0,
                card_holder=current_holder,
                card_number=current_card_number,
                card_name=current_card_name,
                memo=memo or None,
            ))

        return ParsedStatement(transactions=transactions, source_name=cls.SOURCE_NAME)
