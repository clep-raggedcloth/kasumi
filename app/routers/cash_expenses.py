from calendar import monthrange
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.models.database import CashExpense, get_db

router = APIRouter(prefix="/cash-expenses")
templates = Jinja2Templates(directory="app/templates")
CASH_CATEGORIES = ("食費", "日用品", "交通", "医療", "娯楽", "その他")


def _report_redirect(payment_date: date) -> RedirectResponse:
    return RedirectResponse(
        url=f"/report?year={payment_date.year}&month={payment_date.month}",
        status_code=303,
    )


def _success_response(request: Request, payment_date: date) -> JSONResponse | RedirectResponse:
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JSONResponse({"ok": True})
    return _report_redirect(payment_date)


def _fields(merchant: str, amount: int, category: str, memo: str) -> dict:
    merchant = merchant.strip()
    if not merchant:
        raise HTTPException(status_code=422, detail="支払先を入力してください")
    return {
        "merchant": merchant,
        "amount": amount,
        "category": category.strip() or "その他",
        "memo": memo.strip() or None,
    }


def _require_same_month(payment_date: date, year: int, month: int) -> None:
    if (payment_date.year, payment_date.month) != (year, month):
        raise HTTPException(status_code=422, detail="表示中の年月内の支払日を指定してください")


@router.post("/add")
async def add_cash_expense(
    request: Request,
    date: date = Form(...),
    report_year: int = Form(..., ge=1, le=9999),
    report_month: int = Form(..., ge=1, le=12),
    merchant: str = Form(...),
    amount: int = Form(..., gt=0),
    category: str = Form("その他"),
    memo: str = Form(""),
    db: Session = Depends(get_db),
):
    _require_same_month(date, report_year, report_month)
    db.add(CashExpense(date=date, **_fields(merchant, amount, category, memo)))
    db.commit()
    return _success_response(request, date)


@router.get("/{expense_id}/edit", response_class=HTMLResponse)
async def edit_cash_expense_page(
    request: Request,
    expense_id: int,
    db: Session = Depends(get_db),
):
    expense = db.get(CashExpense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="現金払いが見つかりません")
    payment_date = expense.date
    return templates.TemplateResponse("cash_expense_edit.html", {
        "request": request,
        "edit_expense": expense,
        "month_start": payment_date.replace(day=1),
        "month_end": payment_date.replace(day=monthrange(payment_date.year, payment_date.month)[1]),
        "cash_categories": CASH_CATEGORIES,
    })


@router.post("/{expense_id}/edit")
async def edit_cash_expense(
    expense_id: int,
    request: Request,
    date: date = Form(...),
    merchant: str = Form(...),
    amount: int = Form(..., gt=0),
    category: str = Form("その他"),
    memo: str = Form(""),
    db: Session = Depends(get_db),
):
    expense = db.get(CashExpense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="現金払いが見つかりません")
    _require_same_month(date, expense.date.year, expense.date.month)
    expense.date = date
    for field, value in _fields(merchant, amount, category, memo).items():
        setattr(expense, field, value)
    db.commit()
    return _success_response(request, date)


@router.post("/{expense_id}/delete")
async def delete_cash_expense(
    expense_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    expense = db.get(CashExpense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="現金払いが見つかりません")
    payment_date = expense.date
    db.delete(expense)
    db.commit()
    return _success_response(request, payment_date)
