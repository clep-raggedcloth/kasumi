from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.database import get_db, Transaction, FixedExpense, Statement
from app.utils.pdf_generator import render_pdf

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _build_report_context(year: int, month: int, db: Session) -> dict:
    # クレジット明細
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

    # カード名義別に集計
    by_holder: dict[str, list] = {}
    for t in txns:
        key = f"{t.card_holder} / {t.card_name}"
        by_holder.setdefault(key, []).append(t)

    card_total = sum(t.amount for t in txns)
    fixed_total = sum(f.amount for f in fixed)
    grand_total = card_total + fixed_total

    return {
        "year": year,
        "month": month,
        "by_holder": by_holder,
        "fixed_expenses": fixed,
        "card_total": card_total,
        "fixed_total": fixed_total,
        "grand_total": grand_total,
    }


@router.get("/report")
async def report_page(
    request: Request,
    year: int,
    month: int,
    db: Session = Depends(get_db),
):
    ctx = _build_report_context(year, month, db)
    return templates.TemplateResponse("report.html", {"request": request, **ctx})


@router.get("/report/pdf")
async def report_pdf(
    year: int,
    month: int,
    db: Session = Depends(get_db),
):
    ctx = _build_report_context(year, month, db)
    html = templates.get_template("pdf_report.html").render(**ctx)
    pdf_bytes = render_pdf(html)
    filename = f"kasumi_{year}{month:02d}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
