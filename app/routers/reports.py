from calendar import monthrange
from datetime import date, datetime, timezone
from math import cos, radians, sin

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.categories import CATEGORIES, UNCATEGORIZED, merchant_key, validate_category
from app.models.database import get_db, Transaction, FixedExpense, CashExpense, Statement, MerchantCategoryDefault
from app.utils.pdf_generator import render_pdf

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
CHART_COLORS = (
    "#4f46e5", "#0891b2", "#16a34a", "#d97706", "#dc2626", "#9333ea",
    "#0d9488", "#ea580c", "#2563eb", "#65a30d", "#be185d", "#64748b",
    "#78716c",
)


def _category_breakdown(txns: list[Transaction], fixed: list[FixedExpense], cash: list[CashExpense]) -> dict:
    amounts: dict[str, int] = {}
    adjustment_total = 0
    items = [*txns, *fixed, *cash]
    for item in items:
        if item.amount < 0:
            adjustment_total += item.amount
        elif item.amount > 0:
            category = item.category or UNCATEGORIZED
            amounts[category] = amounts.get(category, 0) + item.amount

    total = sum(amounts.values())
    chart = []
    angle = -90.0
    for index, (category, amount) in enumerate(sorted(amounts.items(), key=lambda x: (-x[1], x[0]))):
        sweep = amount * 360 / total
        end = angle + sweep
        if len(amounts) == 1:
            path = None
        else:
            x1 = 100 + 90 * cos(radians(angle))
            y1 = 100 + 90 * sin(radians(angle))
            x2 = 100 + 90 * cos(radians(end))
            y2 = 100 + 90 * sin(radians(end))
            path = f"M 100 100 L {x1:.3f} {y1:.3f} A 90 90 0 {int(sweep > 180)} 1 {x2:.3f} {y2:.3f} Z"
        chart.append({
            "category": category,
            "amount": amount,
            "percent": round(amount * 100 / total, 1),
            "color": CHART_COLORS[index % len(CHART_COLORS)],
            "path": path,
        })
        angle = end
    return {
        "category_chart": chart,
        "category_spend_total": total,
        "adjustment_total": adjustment_total,
    }


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
    breakdown = _category_breakdown(included, fixed, cash)

    return {
        "year": year,
        "month": month,
        "month_start": start,
        "month_end": end,
        "by_holder": by_holder,
        "fixed_expenses": fixed,
        "cash_expenses": cash,
        "edit_expense": None,
        "edit_transaction": None,
        "card_total": card_total,
        "fixed_total": fixed_total,
        "cash_total": cash_total,
        "grand_total": grand_total,
        "cash_categories": CATEGORIES,
        "credit_categories": CATEGORIES,
        **breakdown,
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


@router.get("/transactions/{txn_id}/edit", response_class=HTMLResponse)
async def edit_transaction_page(
    request: Request,
    txn_id: int,
    db: Session = Depends(get_db),
):
    txn = db.get(Transaction, txn_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="クレジット明細が見つかりません")
    return templates.TemplateResponse("transaction_edit.html", {
        "request": request,
        "edit_transaction": txn,
        "credit_categories": CATEGORIES,
    })


@router.post("/transactions/{txn_id}/edit")
async def edit_transaction(
    txn_id: int,
    request: Request,
    category: str = Form(""),
    user_note: str = Form(""),
    db: Session = Depends(get_db),
):
    txn = db.get(Transaction, txn_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="クレジット明細が見つかりません")
    category_value = validate_category(category, txn.category, allow_uncategorized=True)
    note_value = user_note.strip()
    if len(note_value) > 500:
        raise HTTPException(status_code=422, detail="補足は500文字以内で入力してください")

    if category_value != txn.category:
        key = merchant_key(txn.merchant)
        rule = db.get(MerchantCategoryDefault, key)
        if category_value is None:
            if rule is not None:
                db.delete(rule)
        elif rule is None:
            db.add(MerchantCategoryDefault(
                merchant_key=key,
                category=category_value,
                updated_at=datetime.now(timezone.utc).isoformat(),
            ))
        else:
            rule.category = category_value
            rule.updated_at = datetime.now(timezone.utc).isoformat()

    txn.category = category_value
    txn.user_note = note_value or None
    year, month = txn.statement.year, txn.statement.month
    db.commit()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JSONResponse({"ok": True})
    return RedirectResponse(url=f"/report?year={year}&month={month}", status_code=303)


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
