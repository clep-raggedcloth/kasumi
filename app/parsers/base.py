from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional


@dataclass
class ParsedTransaction:
    date: date
    merchant: str
    amount: int
    card_holder: Optional[str] = None
    card_number: Optional[str] = None
    card_name: Optional[str] = None
    memo: Optional[str] = None


@dataclass
class ParsedStatement:
    transactions: List[ParsedTransaction] = field(default_factory=list)
    source_name: str = ""


class BaseParser(ABC):
    """全パーサーの基底クラス。新しいカード会社に対応する際はこれを継承する。"""

    SOURCE_NAME: str = ""

    @classmethod
    @abstractmethod
    def can_parse(cls, content: str) -> bool:
        """このパーサーがファイルを解析できるか判定する"""
        ...

    @classmethod
    @abstractmethod
    def parse(cls, content: str) -> ParsedStatement:
        """CSVコンテンツを解析してParsdStatementを返す"""
        ...


# パーサーレジストリ
_PARSERS: List[type[BaseParser]] = []


def register_parser(cls: type[BaseParser]) -> type[BaseParser]:
    _PARSERS.append(cls)
    return cls


def detect_and_parse(content: str) -> ParsedStatement:
    for parser in _PARSERS:
        if parser.can_parse(content):
            return parser.parse(content)
    raise ValueError("対応しているカード会社のCSVフォーマットが見つかりませんでした。")


def list_sources() -> List[str]:
    return [p.SOURCE_NAME for p in _PARSERS]
