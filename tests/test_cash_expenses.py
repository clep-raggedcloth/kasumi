import unittest
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.main import app
from app.models.database import Base, CashExpense, FixedExpense, get_db
from app.routers.reports import _build_report_context, templates


class CashExpenseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)

        def test_db():
            with Session(self.engine) as session:
                yield session

        app.dependency_overrides[get_db] = test_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_add_edit_delete_and_monthly_totals(self):
        with Session(self.engine) as session:
            session.add(FixedExpense(name="家賃", amount=80000, category="住居", active=True))
            session.commit()

        response = self.client.post("/cash-expenses/add", data={
            "date": "2026-10-01", "merchant": "  スーパー  ", "amount": "1200",
            "report_year": "2026", "report_month": "10",
            "category": "食費", "memo": "  昼食  ",
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/report?year=2026&month=10")

        with Session(self.engine) as session:
            cash = session.scalar(select(CashExpense))
            self.assertEqual((cash.merchant, cash.memo), ("スーパー", "昼食"))
            cash_id = cash.id
            october = _build_report_context(2026, 10, session)
            september = _build_report_context(2026, 9, session)
            self.assertEqual((october["cash_total"], october["grand_total"]), (1200, 81200))
            self.assertEqual((september["cash_total"], september["grand_total"]), (0, 80000))
            pdf_html = templates.get_template("pdf_report.html").render(**october)
            self.assertIn("スーパー", pdf_html)
            self.assertIn("現金払い合計", pdf_html)

        response = self.client.get("/?year=2026&month=10")
        self.assertIn("PDFダウンロード", response.text)
        response = self.client.get("/report?year=2026&month=10")
        self.assertIn("スーパー", response.text)
        self.assertIn('min="2026-10-01" max="2026-10-31"', response.text)
        self.assertIn(f'href="/cash-expenses/{cash_id}/edit"', response.text)

        edit_page = self.client.get(f"/cash-expenses/{cash_id}/edit")
        self.assertEqual(edit_page.status_code, 200)
        self.assertIn('value="2026-10-01"', edit_page.text)
        self.assertIn('value="スーパー"', edit_page.text)
        self.assertIn('min="2026-10-01" max="2026-10-31"', edit_page.text)

        response = self.client.post(f"/cash-expenses/{cash_id}/edit", data={
            "date": "2026-10-30", "merchant": "薬局", "amount": "500",
            "category": "医療", "memo": "",
        }, follow_redirects=False)
        self.assertEqual(response.headers["location"], "/report?year=2026&month=10")
        with Session(self.engine) as session:
            self.assertEqual(_build_report_context(2026, 10, session)["cash_total"], 500)
            self.assertEqual(_build_report_context(2026, 11, session)["cash_total"], 0)

        response = self.client.post(f"/cash-expenses/{cash_id}/delete", follow_redirects=False)
        self.assertEqual(response.headers["location"], "/report?year=2026&month=10")
        with Session(self.engine) as session:
            self.assertEqual(_build_report_context(2026, 10, session)["cash_total"], 0)

    def test_cash_only_month_and_invalid_amount(self):
        response = self.client.get("/?year=2026&month=12")
        self.assertIn("レポート・現金払い", response.text)
        self.assertEqual(self.client.get("/report?year=2026&month=12").status_code, 200)

        response = self.client.post("/cash-expenses/add", data={
            "date": "2026-12-31", "merchant": "公園", "amount": "0",
            "report_year": "2026", "report_month": "12",
        })
        self.assertEqual(response.status_code, 422)
        with Session(self.engine) as session:
            self.assertEqual(session.scalars(select(CashExpense)).all(), [])

        self.client.post("/cash-expenses/add", data={
            "date": "2026-12-31", "merchant": "公園", "amount": "300",
            "report_year": "2026", "report_month": "12",
        })
        response = self.client.get("/?year=2026&month=12")
        self.assertIn("PDFダウンロード", response.text)
        with Session(self.engine) as session:
            self.assertEqual(_build_report_context(2026, 12, session)["cash_total"], 300)

    def test_active_fixed_expense_alone_enables_report_pdf(self):
        with Session(self.engine) as session:
            expense = FixedExpense(name="家賃", amount=80000, category="住居", active=True)
            session.add(expense)
            session.commit()
            expense_id = expense.id

        response = self.client.get("/?year=2026&month=9")
        self.assertIn("PDFダウンロード", response.text)
        self.assertNotIn("データはまだありません", response.text)
        self.assertIn("¥80,000", self.client.get("/report?year=2026&month=9").text)

        with Session(self.engine) as session:
            session.get(FixedExpense, expense_id).active = False
            session.commit()
        response = self.client.get("/?year=2026&month=9")
        self.assertNotIn("PDFダウンロード", response.text)
        self.assertIn("データはまだありません", response.text)

    def test_rejects_dates_outside_report_month_on_add_and_edit(self):
        response = self.client.post("/cash-expenses/add", data={
            "date": "2026-11-01", "report_year": "2026", "report_month": "10",
            "merchant": "スーパー", "amount": "300",
        })
        self.assertEqual(response.status_code, 422)
        self.assertIn("表示中の年月内", response.text)

        self.client.post("/cash-expenses/add", data={
            "date": "2026-10-31", "report_year": "2026", "report_month": "10",
            "merchant": "スーパー", "amount": "300",
        })
        with Session(self.engine) as session:
            cash_id = session.scalar(select(CashExpense.id))

        response = self.client.post(f"/cash-expenses/{cash_id}/edit", data={
            "date": "2026-11-01", "merchant": "薬局", "amount": "500",
        })
        self.assertEqual(response.status_code, 422)
        with Session(self.engine) as session:
            cash = session.get(CashExpense, cash_id)
            self.assertEqual((cash.date, cash.merchant, cash.amount),
                             (date(2026, 10, 31), "スーパー", 300))

    def test_async_requests_return_json_and_updated_report_data(self):
        headers = {"X-Requested-With": "XMLHttpRequest"}
        response = self.client.post("/cash-expenses/add", headers=headers, data={
            "date": "2026-10-01", "report_year": "2026", "report_month": "10",
            "merchant": "スーパー", "amount": "300",
        }, follow_redirects=False)
        self.assertEqual((response.status_code, response.json()), (200, {"ok": True}))
        with Session(self.engine) as session:
            cash_id = session.scalar(select(CashExpense.id))

        report = self.client.get("/report?year=2026&month=10").text
        self.assertIn('id="cash-expenses-section" data-cash-total="300"', report)
        self.assertIn('id="cash-total">¥300', report)

        response = self.client.post(f"/cash-expenses/{cash_id}/edit", headers=headers, data={
            "date": "2026-10-02", "merchant": "薬局", "amount": "500",
        }, follow_redirects=False)
        self.assertEqual((response.status_code, response.json()), (200, {"ok": True}))
        self.assertIn('data-cash-total="500"', self.client.get("/report?year=2026&month=10").text)

        response = self.client.post(f"/cash-expenses/{cash_id}/delete", headers=headers,
                                    follow_redirects=False)
        self.assertEqual((response.status_code, response.json()), (200, {"ok": True}))
        self.assertIn('data-cash-total="0"', self.client.get("/report?year=2026&month=10").text)


if __name__ == "__main__":
    unittest.main()
