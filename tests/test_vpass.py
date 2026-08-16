import unittest

from app.parsers.vpass import VpassParser


HEADER = "利用者　様,4980-11**-****-****,テストカード"


class VpassParserTests(unittest.TestCase):
    def test_parses_unquoted_comma_in_merchant(self):
        content = "\n".join([
            HEADER,
            "2026/07/09,GITHUB, INC. (GITHUB.COM ),695,１,１,695,4.13 USD",
            ",,,,,695",
        ])

        parsed = VpassParser.parse(content)

        self.assertEqual(len(parsed.transactions), 1)
        transaction = parsed.transactions[0]
        self.assertEqual(transaction.merchant, "GITHUB, INC. (GITHUB.COM )")
        self.assertEqual(transaction.amount, 695)
        self.assertEqual(transaction.memo, "4.13 USD")

    def test_parses_cashback_with_only_billed_amount(self):
        content = "\n".join([
            HEADER,
            "2026/06/30,キャッシュバック（ポイント交換）,,,,-49029,",
            ",,,,,-49029",
        ])

        parsed = VpassParser.parse(content)

        self.assertEqual(len(parsed.transactions), 1)
        self.assertEqual(parsed.transactions[0].amount, -49029)

    def test_preserves_numeric_comma_separated_merchant_fragment(self):
        content = "\n".join([
            HEADER,
            "2026/07/09,店舗,123,695,１,１,695,備考",
            ",,,,,695",
        ])

        parsed = VpassParser.parse(content)

        self.assertEqual(parsed.transactions[0].merchant, "店舗,123")
        self.assertEqual(parsed.transactions[0].amount, 695)

    def test_parses_unquoted_comma_in_memo_when_unambiguous(self):
        content = "\n".join([
            HEADER,
            "2026/07/09,店舗A,695,１,１,695,備考前半,備考後半",
            ",,,,,695",
        ])

        parsed = VpassParser.parse(content)

        self.assertEqual(parsed.transactions[0].merchant, "店舗A")
        self.assertEqual(parsed.transactions[0].amount, 695)
        self.assertEqual(parsed.transactions[0].memo, "備考前半,備考後半")

    def test_rejects_numeric_memo_when_column_structure_is_ambiguous(self):
        content = "\n".join([
            HEADER,
            "2026/07/09,店舗A,50,１,１,50,50,備考後半",
            ",,,,,50",
        ])

        with self.assertRaisesRegex(ValueError, "一意に特定できません"):
            VpassParser.parse(content)

    def test_validates_multiple_section_subtotals_against_grand_total(self):
        content = "\n".join([
            HEADER,
            "2026/07/01,店舗A,400,１,１,400,",
            ",,,,,400",
            "別利用者　様,4980-22**-****-****,テストカード",
            "2026/07/02,店舗B,600,１,１,600,",
            ",,,,,600",
            ",,,,,1000,",
        ])

        parsed = VpassParser.parse(content)

        self.assertEqual(len(parsed.transactions), 2)
        self.assertEqual(sum(t.amount for t in parsed.transactions), 1000)

    def test_rejects_total_mismatch(self):
        content = "\n".join([
            HEADER,
            "2026/07/01,店舗A,400,１,１,400,",
            ",,,,,401",
        ])

        with self.assertRaisesRegex(ValueError, "明細合計: 400円、CSV合計: 401円"):
            VpassParser.parse(content)

    def test_rejects_malformed_transaction_instead_of_storing_zero(self):
        content = "\n".join([
            HEADER,
            "2026/07/01,店舗A,不明,１,１,不明,",
        ])

        with self.assertRaisesRegex(ValueError, "2行目"):
            VpassParser.parse(content)

    def test_rejects_csv_without_transactions(self):
        with self.assertRaisesRegex(ValueError, "読み取り可能な明細がありません"):
            VpassParser.parse(HEADER)


if __name__ == "__main__":
    unittest.main()
