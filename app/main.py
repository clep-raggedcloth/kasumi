from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Depends, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.database import init_db, get_db, Statement, FixedExpense, CashExpense
from app.routers import upload, expenses, reports, cash_expenses

app = FastAPI(title="Kasumi", description="家計報告書アプリ")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(upload.router)
app.include_router(expenses.router)
app.include_router(reports.router)
app.include_router(cash_expenses.router)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    year: int | None = Query(None, ge=1, le=9999),
    month: int | None = Query(None, ge=1, le=12),
    error: str = None,
    db: Session = Depends(get_db),
):
    previous_month = datetime.now(ZoneInfo("Asia/Tokyo")).date().replace(day=1) - timedelta(days=1)
    year = year if year is not None else previous_month.year
    month = month if month is not None else previous_month.month

    statements = db.scalars(
        select(Statement).order_by(Statement.year.desc(), Statement.month.desc())
    ).all()

    # 選択月の件数
    statement_id = db.scalar(
        select(Statement.id)
        .where(Statement.year == year, Statement.month == month)
        .limit(1)
    )
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    cash_id = db.scalar(
        select(CashExpense.id)
        .where(CashExpense.date >= start, CashExpense.date <= end)
        .limit(1)
    )
    fixed_id = db.scalar(
        select(FixedExpense.id)
        .where(FixedExpense.active.is_(True))
        .limit(1)
    )
    has_data = any(item is not None for item in (statement_id, cash_id, fixed_id))

    return templates.TemplateResponse("index.html", {
        "request": request,
        "year": year,
        "month": month,
        "statements": statements,
        "has_data": has_data,
        "error": error,
    })


@app.get("/fixed-expenses", response_class=HTMLResponse)
async def fixed_expenses_page(request: Request, db: Session = Depends(get_db)):
    expenses = db.scalars(select(FixedExpense).order_by(FixedExpense.id)).all()
    return templates.TemplateResponse("fixed_expenses.html", {
        "request": request,
        "expenses": expenses,
        "total": sum(e.amount for e in expenses if e.active),
    })
