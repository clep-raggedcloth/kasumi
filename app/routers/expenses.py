from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.models.database import get_db, FixedExpense

router = APIRouter(prefix="/fixed-expenses")


@router.post("/add")
async def add_fixed_expense(
    name: str = Form(...),
    amount: int = Form(...),
    category: str = Form(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
):
    db.add(FixedExpense(name=name, amount=amount, category=category, note=note or None))
    db.commit()
    return RedirectResponse(url="/fixed-expenses", status_code=303)


@router.post("/{expense_id}/toggle")
async def toggle_fixed_expense(
    expense_id: int,
    db: Session = Depends(get_db),
):
    expense = db.get(FixedExpense, expense_id)
    if expense:
        expense.active = not expense.active
        db.commit()
    return RedirectResponse(url="/fixed-expenses", status_code=303)


@router.post("/{expense_id}/delete")
async def delete_fixed_expense(
    expense_id: int,
    db: Session = Depends(get_db),
):
    expense = db.get(FixedExpense, expense_id)
    if expense:
        db.delete(expense)
        db.commit()
    return RedirectResponse(url="/fixed-expenses", status_code=303)
