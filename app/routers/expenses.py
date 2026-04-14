from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.models.database import get_db, FixedExpense

router = APIRouter(prefix="/fixed-expenses")


def _redirect_to_fixed_expenses(request: Request) -> RedirectResponse:
    url = str(request.base_url) + "fixed-expenses"
    return RedirectResponse(url=url, status_code=303)


@router.post("/add")
async def add_fixed_expense(
    request: Request,
    name: str = Form(...),
    amount: int = Form(...),
    category: str = Form(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
):
    db.add(FixedExpense(name=name, amount=amount, category=category, note=note or None))
    db.commit()
    return _redirect_to_fixed_expenses(request)


@router.post("/{expense_id}/toggle")
async def toggle_fixed_expense(
    request: Request,
    expense_id: int,
    db: Session = Depends(get_db),
):
    expense = db.get(FixedExpense, expense_id)
    if expense:
        expense.active = not expense.active
        db.commit()
    return _redirect_to_fixed_expenses(request)


@router.post("/{expense_id}/delete")
async def delete_fixed_expense(
    request: Request,
    expense_id: int,
    db: Session = Depends(get_db),
):
    expense = db.get(FixedExpense, expense_id)
    if expense:
        db.delete(expense)
        db.commit()
    return _redirect_to_fixed_expenses(request)
