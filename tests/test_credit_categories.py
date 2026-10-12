import io
import tempfile
import unittest
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.main import app
from app.models import database
from app.models.database import (
    Base, CashExpense, FixedExpense, MerchantCategoryDefault, Statement,
    Transaction, get_db,
)
from app.routers.reports import _build_report_context, templates


class CreditCategoryTests(unittest.TestCase):
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

    def _statement(self, year=2026, month=10):
        return Statement(
            filename="test.csv", card_source="vpass", year=year, month=month,
            uploaded_at="2026-10-12T00:00:00",
        )

    def test_edit_learns_default_and_preserves_csv_memo(self):
        with Session(self.engine) as session:
            stmt = self._statement()
            stmt.transactions.append(Transaction(
                date=date(2026, 10, 1), merchant="Ａｍａｚｏｎ  ＣＯ．ＪＰ",
                amount=3000, memo="CSV備考", card_holder="利用者", card_name="カード",
            ))
            session.add(stmt)
            session.commit()
            txn_id = stmt.transactions[0].id

        page = self.client.get(f"/transactions/{txn_id}/edit")
        self.assertEqual(page.status_code, 200)
        self.assertIn("未分類", page.text)
        self.assertNotIn("CSV備考", page.text)

        response = self.client.post(f"/transactions/{txn_id}/edit", data={
            "category": "日用品", "user_note": "  洗剤と電池  ",
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/report?year=2026&month=10")

        with Session(self.engine) as session:
            txn = session.get(Transaction, txn_id)
            self.assertEqual((txn.category, txn.user_note, txn.memo), ("日用品", "洗剤と電池", "CSV備考"))
            rule = session.scalar(select(MerchantCategoryDefault))
            self.assertEqual((rule.merchant_key, rule.category), ("AMAZON CO.JP", "日用品"))

        report = self.client.get("/report?year=2026&month=10").text
        self.assertIn("洗剤と電池", report)
        self.assertNotIn("CSV備考", report)
        self.assertIn("カテゴリ別の支出", report)
        self.assertIn("100.0%", report)
        with Session(self.engine) as session:
            html = templates.get_template("pdf_report.html").render(**_build_report_context(2026, 10, session, pdf=True))
        self.assertIn("洗剤と電池", html)
        self.assertIn("日用品", html)
        self.assertNotIn("CSV備考", html)

        csv = "\n".join([
            "利用者　様,4980-11**-****-****,テストカード",
            "2026/11/01,Amazon CO.JP,800,１,１,800,",
            ",,,,,800",
        ])
        upload = self.client.post("/upload", data={"year": "2026", "month": "11"},
                                  files={"file": ("nov.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
                                  follow_redirects=False)
        self.assertEqual(upload.status_code, 303)
        with Session(self.engine) as session:
            november = session.scalar(select(Transaction).join(Statement).where(Statement.month == 11))
            self.assertEqual(november.category, "日用品")
            self.assertIsNone(november.user_note)

        self.client.post(f"/transactions/{txn_id}/edit", data={"category": "", "user_note": "洗剤"})
        with Session(self.engine) as session:
            self.assertIsNone(session.get(Transaction, txn_id).category)
            self.assertIsNone(session.scalar(select(MerchantCategoryDefault)))
            november = session.scalar(select(Transaction).join(Statement).where(Statement.month == 11))
            self.assertEqual(november.category, "日用品")

    def test_category_totals_include_all_negative_adjustments_and_exclusions(self):
        with Session(self.engine) as session:
            stmt = self._statement()
            stmt.transactions.extend([
                Transaction(date=date(2026, 10, 1), merchant="Amazon", amount=3000, category="日用品"),
                Transaction(date=date(2026, 10, 2), merchant="返金", amount=-1000, category="日用品"),
                Transaction(date=date(2026, 10, 3), merchant="対象外", amount=800, category="食費", excluded=True),
            ])
            session.add_all([
                stmt,
                FixedExpense(name="家賃", amount=5000, category="住居", active=True),
                FixedExpense(name="調整", amount=-200, category="住居", active=True),
                CashExpense(date=date(2026, 10, 3), merchant="スーパー", amount=400, category="食費"),
                CashExpense(date=date(2026, 10, 4), merchant="返金", amount=-100, category="食費"),
            ])
            session.commit()
            context = _build_report_context(2026, 10, session)

        self.assertEqual(context["category_spend_total"], 8400)
        self.assertEqual(context["adjustment_total"], -1300)
        self.assertEqual(context["grand_total"], 7100)
        self.assertEqual(sum(item["amount"] for item in context["category_chart"]), 8400)
        self.assertEqual(context["category_spend_total"] + context["adjustment_total"], context["grand_total"])
        self.assertEqual({item["category"] for item in context["category_chart"]}, {"日用品", "住居", "食費"})

    def test_inline_edit_markup_and_async_save(self):
        with Session(self.engine) as session:
            stmt = self._statement()
            stmt.transactions.append(Transaction(
                date=date(2026, 10, 1), merchant="Amazon", amount=3000,
                memo="元のCSV備考",
            ))
            session.add(stmt)
            session.commit()
            txn_id = stmt.transactions[0].id

        report = self.client.get("/report?year=2026&month=10").text
        self.assertIn(f'form="credit-form-{txn_id}"', report)
        self.assertIn(f'id="credit-form-{txn_id}"', report)
        self.assertIn('name="category"', report)
        self.assertIn('name="user_note"', report)
        self.assertIn('type="text" id="credit-note-', report)
        self.assertNotIn("元のCSV備考", report)
        self.assertNotIn('id="credit-edit-dialog"', report)

        headers = {"X-Requested-With": "XMLHttpRequest"}
        response = self.client.post(f"/transactions/{txn_id}/edit", headers=headers, data={
            "category": "日用品", "user_note": "洗剤",
        }, follow_redirects=False)
        self.assertEqual((response.status_code, response.json()), (200, {"ok": True}))
        with Session(self.engine) as session:
            updated_at = session.scalar(select(MerchantCategoryDefault)).updated_at
            self.assertEqual(session.get(Transaction, txn_id).user_note, "洗剤")

        response = self.client.post(f"/transactions/{txn_id}/edit", headers=headers, data={
            "category": "日用品", "user_note": "電池",
        })
        self.assertEqual(response.status_code, 200)
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(MerchantCategoryDefault)).updated_at, updated_at)
            self.assertEqual(session.get(Transaction, txn_id).user_note, "電池")

        response = self.client.post(f"/transactions/{txn_id}/edit", headers=headers, data={
            "category": "無効", "user_note": "変更しない",
        })
        self.assertEqual(response.status_code, 422)
        with Session(self.engine) as session:
            self.assertEqual(session.get(Transaction, txn_id).user_note, "電池")

    def test_pdf_renders_when_native_libraries_are_available(self):
        try:
            from weasyprint import HTML  # noqa: F401
        except OSError:
            self.skipTest("PDF用のPangoライブラリがありません")

        with Session(self.engine) as session:
            stmt = self._statement()
            stmt.transactions.append(Transaction(
                date=date(2026, 10, 1), merchant="Amazon", amount=3000,
                category="日用品", user_note="洗剤と電池", memo="CSV備考",
            ))
            session.add(stmt)
            session.commit()

        pdf = self.client.get("/report/pdf?year=2026&month=10")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_rejects_invalid_inputs_and_keeps_legacy_category(self):
        with Session(self.engine) as session:
            stmt = self._statement()
            stmt.transactions.append(Transaction(
                date=date(2026, 10, 1), merchant="古い店", amount=100,
                category="旧カテゴリ",
            ))
            session.add(stmt)
            session.commit()
            txn_id = stmt.transactions[0].id

        self.assertEqual(self.client.post(f"/transactions/{txn_id}/edit", data={
            "category": "不正", "user_note": "備考",
        }).status_code, 422)
        self.assertEqual(self.client.post(f"/transactions/{txn_id}/edit", data={
            "category": "旧カテゴリ", "user_note": "あ" * 501,
        }).status_code, 422)
        self.assertEqual(self.client.post(f"/transactions/{txn_id}/edit", data={
            "category": "旧カテゴリ", "user_note": "補足",
        }, follow_redirects=False).status_code, 303)
        with Session(self.engine) as session:
            self.assertEqual(session.get(Transaction, txn_id).category, "旧カテゴリ")
            self.assertIsNone(session.scalar(select(MerchantCategoryDefault)))

        self.assertEqual(self.client.post("/fixed-expenses/add", data={
            "name": "家賃", "amount": "100", "category": "不正",
        }).status_code, 422)
        self.assertEqual(self.client.post("/cash-expenses/add", data={
            "date": "2026-10-01", "merchant": "店", "amount": "100",
            "report_year": "2026", "report_month": "10", "category": "不正",
        }).status_code, 422)


class DatabaseMigrationTests(unittest.TestCase):
    def test_adds_user_note_to_existing_database(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "old.db"
            old_engine = create_engine(f"sqlite:///{db_path}")
            with old_engine.begin() as connection:
                connection.execute(text("CREATE TABLE transactions (id INTEGER PRIMARY KEY, memo TEXT, category TEXT, excluded BOOLEAN DEFAULT 0)"))
                connection.execute(text("INSERT INTO transactions (memo, category, excluded) VALUES ('CSV備考', NULL, 1)"))
            old_engine.dispose()

            original_engine = database.engine
            database.engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
            try:
                database.init_db()
                database.init_db()
                columns = {column["name"] for column in inspect(database.engine).get_columns("transactions")}
                self.assertIn("user_note", columns)
                self.assertIn("merchant_category_defaults", inspect(database.engine).get_table_names())
                with database.engine.connect() as connection:
                    row = connection.execute(text("SELECT memo, category, excluded, user_note FROM transactions")).one()
                    self.assertEqual(row, ("CSV備考", None, 1, None))
            finally:
                database.engine.dispose()
                database.engine = original_engine
