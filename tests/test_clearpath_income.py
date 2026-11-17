"""Regression coverage for paystub annualization and its effect on DTI."""
from datetime import date
import unittest

from apps.clearpath.income import income_check, monthly_income


class PaystubIncomeTests(unittest.TestCase):
    def test_biweekly_income_does_not_trigger_unnecessary_dti_referral(self):
        # Pattern evidence: trace bc2a2fd54a6c4f6db7b4f9948a055ee0.
        check = income_check(
            extraction={
                "doc_type": "paystub",
                "employee_name": "Test Borrower",
                "gross_this_period": 3400,
                "pay_frequency": "biweekly",
                "pay_date": "2026-11-06",
            },
            loan={
                "borrower": {"name": "Test Borrower"},
                "monthly_debts": 720,
                "proposed_housing_payment": 2450,
                "max_dti": 0.45,
            },
            condition={"type": "paystub"},
            as_of=date(2026, 11, 11),
        )

        self.assertEqual(check["monthly_income"], 7366.67)
        self.assertEqual(check["dti"], 0.4303)
        self.assertLess(check["dti"], check["max_dti"])

    def test_semimonthly_still_uses_twenty_four_paychecks(self):
        self.assertEqual(
            monthly_income({
                "doc_type": "paystub",
                "gross_this_period": 3400,
                "pay_frequency": "semimonthly",
            }),
            6800,
        )


if __name__ == "__main__":
    unittest.main()
