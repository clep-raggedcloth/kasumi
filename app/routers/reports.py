from calendar import monthrange
from datetime import date

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.database import get_db, Transaction, FixedExpense, CashExpense, Statement
from app.routers.cash_expenses import CASH_CATEGORIES
from app.utils.pdf_generator import render_pdf

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _build_report_context(year: int, month: int, db: Session, pdf: bool = False) -> dict:
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    # クレジット明細（全件取得）
    txns = db.scalars(
        select(Transaction)
        .join(Statement)
        .where(Statement.year == year, Statement.month == month)
        .order_by(Transaction.date)
    ).all()

    # 固定費
    fixed = db.scalars(
        select(FixedExpense).where(FixedExpense.active == True)  # noqa: E712
    ).all()

    cash = db.scalars(
        select(CashExpense)
        .where(CashExpense.date >= start, CashExpense.date <= end)
        .order_by(CashExpense.date, CashExpense.id)
    ).all()

    # カード名義別にグループ化（PDF時は除外済みを含めない）
    by_holder: dict[str, list] = {}
    for t in txns:
        if pdf and t.excluded:
            continue
        key = f"{t.card_holder} / {t.card_name}"
        by_holder.setdefault(key, []).append(t)

    included = [t for t in txns if not t.excluded]
    card_total = sum(t.amount for t in included)
    fixed_total = sum(f.amount for f in fixed)
    cash_total = sum(c.amount for c in cash)
    grand_total = card_total + fixed_total + cash_total

    return {
        "year": year,
        "month": month,
        "month_start": start,
        "month_end": end,
        "by_holder": by_holder,
        "fixed_expenses": fixed,
        "cash_expenses": cash,
        "edit_expense": None,
        "card_total": card_total,
        "fixed_total": fixed_total,
        "cash_total": cash_total,
        "grand_total": grand_total,
        "cash_categories": CASH_CATEGORIES,
    }


@router.get("/report")
async def report_page(
    request: Request,
    year: int = Query(..., ge=1, le=9999),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
):
    ctx = _build_report_context(year, month, db)
    return templates.TemplateResponse("report.html", {"request": request, **ctx})


@router.post("/transactions/{txn_id}/exclude")
async def toggle_exclude(txn_id: int, db: Session = Depends(get_db)):
    txn = db.get(Transaction, txn_id)
    if not txn:
        return JSONResponse({"error": "not found"}, status_code=404)
    txn.excluded = not txn.excluded
    db.commit()
    return JSONResponse({"excluded": txn.excluded, "amount": txn.amount})


@router.get("/report/pdf")
async def report_pdf(
    year: int = Query(..., ge=1, le=9999),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
):
    ctx = _build_report_context(year, month, db, pdf=True)
    html = templates.get_template("pdf_report.html").render(**ctx)
    pdf_bytes = render_pdf(html)
    filename = f"kasumi_{year}{month:02d}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
