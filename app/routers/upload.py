import os
from datetime import datetime, date
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, UploadFile, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.models.database import get_db, Statement, Transaction
from app.parsers.base import detect_and_parse, list_sources
from app.parsers import vpass  # noqa: F401 — パーサーの登録をトリガー

router = APIRouter()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")


def _decode_statement_csv(raw: bytes) -> str:
    """対応する文字コードを決定的な順序で試してCSVを文字列化する。"""
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise ValueError(
        "CSVの文字コードを読み取れませんでした。"
        "UTF-8またはShift_JIS形式のCSVを指定してください。"
    )


@router.post("/upload")
async def upload_statement(
    request: Request,
    file: UploadFile = File(...),
    year: int = Form(...),
    month: int = Form(...),
    db: Session = Depends(get_db),
):
    raw = await file.read()

    try:
        content = _decode_statement_csv(raw)
        parsed = detect_and_parse(content)
    except ValueError as e:
        params = urlencode({"year": year, "month": month, "error": str(e)})
        return RedirectResponse(url=f"{str(request.base_url)}?{params}", status_code=303)

    stmt = Statement(
        filename=file.filename,
        card_source=parsed.source_name,
        year=year,
        month=month,
        uploaded_at=datetime.now().isoformat(),
    )
    try:
        db.add(stmt)
        db.flush()

        for t in parsed.transactions:
            db.add(Transaction(
                statement_id=stmt.id,
                card_holder=t.card_holder,
                card_number=t.card_number,
                card_name=t.card_name,
                date=t.date,
                merchant=t.merchant,
                amount=t.amount,
                memo=t.memo,
            ))

        db.commit()
    except Exception:
        db.rollback()
        raise
    base = str(request.base_url)
    return RedirectResponse(url=f"{base}?year={year}&month={month}", status_code=303)


@router.post("/statements/{statement_id}/delete")
async def delete_statement(
    request: Request,
    statement_id: int,
    db: Session = Depends(get_db),
):
    stmt = db.get(Statement, statement_id)
    if stmt:
        db.delete(stmt)
        db.commit()
    return RedirectResponse(url=str(request.base_url), status_code=303)
