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


def _parse_transaction_fields(row: list[str], line_number: int) -> tuple[str, int, Optional[str]]:
    """通常の7列は固定位置、超過列は店舗名中のカンマとして厳密に解析する。"""
    if len(row) == 7:
        merchant = row[1].strip()
        billed_amount = _parse_amount(row[5])
        memo = row[6].strip()
        if merchant and billed_amount is not None:
            return merchant, billed_amount, memo or None

    elif len(row) > 7:
        candidates: list[tuple[str, int, Optional[str]]] = []

        for amount_index in range(2, len(row) - 3):
            used_amount = _parse_amount(row[amount_index])
            payment_count = _parse_amount(row[amount_index + 1])
            billing_count = _parse_amount(row[amount_index + 2])
            billed_amount = _parse_amount(row[amount_index + 3])
            merchant = ",".join(row[1:amount_index]).strip()
            memo = ",".join(row[amount_index + 4:]).strip()

            if (
                merchant
                and used_amount is not None
                and payment_count is not None
                and 0 <= payment_count <= 99
                and billing_count is not None
                and 0 <= billing_count <= 99
                and billed_amount is not None
            ):
                candidates.append((merchant, billed_amount, memo or None))

        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise ValueError(
                f"CSVの{line_number}行目の列構造を一意に特定できませんでした。"
            )

    raise ValueError(
        f"CSVの{line_number}行目から金額と支払情報を読み取れませんでした。"
    )


def _declared_total(subtotals: list[int]) -> Optional[int]:
    """単一合計、または名義別小計の和と一致する最終合計を返す。"""
    if len(subtotals) == 1:
        return subtotals[0]
    if len(subtotals) >= 2 and sum(subtotals[:-1]) == subtotals[-1]:
        return subtotals[-1]
    return None


@register_parser
class VpassParser(BaseParser):
    SOURCE_NAME = "vpass"

    @classmethod
    def can_parse(cls, content: str) -> bool:
        return "様," in content[:500]

    @classmethod
    def parse(cls, content: str) -> ParsedStatement:
        reader = csv.reader(io.StringIO(content))

        transactions: list[ParsedTransaction] = []
        subtotals: list[int] = []
        current_holder: Optional[str] = None
        current_card_number: Optional[str] = None
        current_card_name: Optional[str] = None

        for row in reader:
            line_number = reader.line_num

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
                subtotal = _parse_amount(row[5])
                if subtotal is not None:
                    subtotals.append(subtotal)
                continue

            # データ行: 先頭が日付形式
            date_str = row[0].strip()
            if not date_str:
                continue
            try:
                txn_date = datetime.strptime(date_str, "%Y/%m/%d").date()
            except ValueError:
                continue

            merchant, amount, memo = _parse_transaction_fields(row, line_number)

            transactions.append(ParsedTransaction(
                date=txn_date,
                merchant=merchant,
                amount=amount,
                card_holder=current_holder,
                card_number=current_card_number,
                card_name=current_card_name,
                memo=memo,
            ))

        if not transactions:
            raise ValueError("CSVに読み取り可能な明細がありませんでした。")

        declared_total = _declared_total(subtotals)
        actual_total = sum(t.amount for t in transactions)
        if declared_total is not None and actual_total != declared_total:
            raise ValueError(
                "CSVの明細合計が合計行と一致しません。"
                f"明細合計: {actual_total:,}円、CSV合計: {declared_total:,}円"
            )

        return ParsedStatement(transactions=transactions, source_name=cls.SOURCE_NAME)
