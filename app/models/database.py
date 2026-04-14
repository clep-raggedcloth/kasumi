import os
from datetime import date
from typing import Optional, List
from sqlalchemy import create_engine, Column, Integer, String, Date, Boolean, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/kasumi.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


class Base(DeclarativeBase):
    pass


class Statement(Base):
    """アップロードされたクレジット明細ファイル"""
    __tablename__ = "statements"

    id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=False)
    card_source = Column(String, nullable=False)  # e.g. "vpass"
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    uploaded_at = Column(String, nullable=False)

    transactions = relationship("Transaction", back_populates="statement", cascade="all, delete-orphan")


class Transaction(Base):
    """クレジット明細の各行"""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    statement_id = Column(Integer, ForeignKey("statements.id"), nullable=False)
    card_holder = Column(String)          # 名義人
    card_number = Column(String)          # カード番号（マスク済み）
    card_name = Column(String)            # カード名称
    date = Column(Date, nullable=False)
    merchant = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)
    memo = Column(String)
    category = Column(String)             # カテゴリ（手動or自動）

    statement = relationship("Statement", back_populates="transactions")


class FixedExpense(Base):
    """固定費（家賃・水道代など口座引き落とし）"""
    __tablename__ = "fixed_expenses"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)       # 名称（例：家賃）
    amount = Column(Integer, nullable=False)    # 金額
    category = Column(String, nullable=False)  # カテゴリ
    active = Column(Boolean, default=True)      # 有効/無効
    note = Column(String)                       # 備考


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    with Session(engine) as session:
        yield session
