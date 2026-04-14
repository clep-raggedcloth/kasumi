from datetime import date
from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.database import init_db, get_db, Statement, FixedExpense, Transaction
from app.routers import upload, expenses, reports

app = FastAPI(title="Kasumi", description="家計報告書アプリ")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(upload.router)
app.include_router(expenses.router)
app.include_router(reports.router)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    year: int = None,
    month: int = None,
    db: Session = Depends(get_db),
):
    today = date.today()
    year = year or today.year
    month = month or today.month

    statements = db.scalars(
        select(Statement).order_by(Statement.year.desc(), Statement.month.desc())
    ).all()

    # 選択月の件数
    txn_count = db.scalar(
        select(Statement.id)
        .where(Statement.year == year, Statement.month == month)
        .limit(1)
    )
    has_data = txn_count is not None

    return templates.TemplateResponse("index.html", {
        "request": request,
        "year": year,
        "month": month,
        "statements": statements,
        "has_data": has_data,
    })


@app.get("/fixed-expenses", response_class=HTMLResponse)
async def fixed_expenses_page(request: Request, db: Session = Depends(get_db)):
    expenses = db.scalars(select(FixedExpense).order_by(FixedExpense.id)).all()
    return templates.TemplateResponse("fixed_expenses.html", {
        "request": request,
        "expenses": expenses,
        "total": sum(e.amount for e in expenses if e.active),
    })
