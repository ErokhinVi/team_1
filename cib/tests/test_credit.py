"""Money invariants, decision boundaries, and backend failure behavior."""

import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from src import main
from src.credit import ClientData, CreditRequest, HistoryData, decide, payment_schedule


def person(**changes):
    data = dict(id="c-01000", age=30, segment="mass", income_rub=100000,
                risk_score=0.2, has_overdue_history=False)
    data.update(changes)
    return ClientData(**data)


def history(**changes):
    data = dict(client_id="c-01000", total=0, active_count=0,
                active_monthly_payment_rub=0, max_overdue_days=0, has_overdue=False)
    data.update(changes)
    return HistoryData(**data)


def request(**changes):
    data = dict(client_id="c-01000", amount_rub=100000, term_months=12)
    data.update(changes)
    return CreditRequest(**data)


class MoneyTests(unittest.TestCase):
    def test_known_annuity_and_balances(self):
        rows = payment_schedule(Decimal("100000"), 12, Decimal("12"))
        self.assertEqual(rows[0]["payment_rub"], Decimal("8884.88"))
        self.assertEqual(rows[-1]["balance_rub"], 0)
        self.assertEqual(sum(row["principal_rub"] for row in rows), Decimal("100000"))
        self.assertTrue(all(row["balance_rub"] >= 0 for row in rows))
        self.assertTrue(all(row["payment_rub"] == row["principal_rub"] + row["interest_rub"] for row in rows))

    def test_zero_rate_last_installment_absorbs_rounding(self):
        rows = payment_schedule(Decimal("100000"), 12, Decimal(0))
        self.assertEqual(rows[0]["payment_rub"], Decimal("8333.33"))
        self.assertEqual(rows[-1]["payment_rub"], Decimal("8333.37"))
        self.assertEqual(sum(row["payment_rub"] for row in rows), Decimal("100000"))

    def test_money_invariants_across_product_boundaries(self):
        for amount in (Decimal("30000"), Decimal("123456.78"), Decimal("3000000")):
            for term in (6, 12, 60):
                for rate in (Decimal("19.9"), Decimal("24.9")):
                    with self.subTest(amount=amount, term=term, rate=rate):
                        rows = payment_schedule(amount, term, rate)
                        self.assertEqual(rows[-1]["balance_rub"], 0)
                        self.assertEqual(sum(x["principal_rub"] for x in rows), amount)
                        self.assertTrue(all(x["payment_rub"] == x["payment_rub"].quantize(Decimal(".01")) for x in rows))


class DecisionTests(unittest.TestCase):
    def test_no_history_is_not_automatic_rejection(self):
        result = decide(request(), person(), history())
        self.assertTrue(result.approved)
        self.assertEqual(result.status, result.decision)
        self.assertEqual(result.decision_scope, "preliminary")
        self.assertFalse(result.can_disburse)

    def test_existing_payments_change_approval(self):
        result = decide(request(), person(), history(total=1, active_count=1, active_monthly_payment_rub=40000))
        self.assertEqual(result.decision, "rejected")
        self.assertEqual(result.reason_code, "debt_burden")

    def test_counteroffer_fits_budget_including_last_installment(self):
        result = decide(request(amount_rub=1000000, term_months=24), person(income_rub=40000), history())
        self.assertEqual(result.decision, "counteroffer")
        self.assertFalse(result.approved)
        offer = result.counter_offer
        self.assertLess(offer.amount_rub, result.amount_rub)
        self.assertLessEqual(max(offer.monthly_payment_rub, offer.last_payment_rub), Decimal("16000"))
        self.assertEqual(offer.term_months, 24)

    def test_risk_and_historical_arrears_boundaries(self):
        self.assertEqual(decide(request(), person(risk_score="0.65"), history()).reason_code, "risk")
        self.assertEqual(decide(request(), person(), history(total=1, max_overdue_days=60, has_overdue=True)).reason_code, "overdue_history")
        self.assertTrue(decide(request(), person(has_overdue_history=True), history(total=1, max_overdue_days=5, has_overdue=True)).approved)

    def test_scope_and_no_income(self):
        for changes, code in [({"age": 17}, "age"), ({"segment": "sme"}, "product_scope"), ({"income_rub": 0}, "income")]:
            with self.subTest(changes=changes):
                result = decide(request(), person(**changes), history())
                self.assertFalse(result.approved)
                self.assertEqual(result.reason_code, code)

    def test_explicit_current_arrears_prevent_approval(self):
        result = decide(request(), person(), history(summary={'has_active_overdue': True}))
        self.assertFalse(result.approved)
        self.assertEqual(result.reason_code, 'current_overdue')

    def test_wrong_client_cannot_receive_another_clients_decision(self):
        with self.assertRaises(ValueError):
            decide(request(), person(id="c-01001"), history())


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()

    def test_catalog_keeps_existing_products_and_adds_credit(self):
        data = self.client.get('/products').json()
        self.assertEqual(data['total'], 3)
        self.assertEqual({x['id'] for x in data['items']}, {'card-debit', 'deposit-base', 'consumer_credit'})
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_quote_is_numeric_and_does_not_access_backend(self):
        with patch.object(main, 'load_credit_data', new_callable=AsyncMock) as load:
            response = self.client.post('/credit/calculate', json={'amount_rub': '100000.00', 'term_months': 12})
            self.assertEqual(response.status_code, 200)
            self.assertIsInstance(response.json()['monthly_payment_rub'], (int, float))
            load.assert_not_awaited()

    def test_invalid_input_is_rejected_before_data_lookup(self):
        payload = {'client_id': 'c-01000', 'amount_rub': 100000, 'term_months': 12}
        cases = [
            {'amount_rub': True}, {'amount_rub': 'NaN'}, {'amount_rub': 'Infinity'},
            {'amount_rub': -1}, {'amount_rub': 3000001}, {'amount_rub': '30000.001'},
            {'term_months': True}, {'term_months': 12.5}, {'term_months': 0},
            {'client_id': '../clients'}, {'income_rub': 999999},
        ]
        with patch.object(main, 'load_credit_data', new_callable=AsyncMock) as load:
            for change in cases:
                with self.subTest(change=change):
                    response = self.client.post('/credit/decide', json={**payload, **change})
                    self.assertEqual(response.status_code, 422)
            load.assert_not_awaited()

    def backend_response(self, status, data):
        return httpx.Response(status, json=data)

    def test_decision_reads_only_client_and_history(self):
        get = AsyncMock(side_effect=[
            self.backend_response(200, person().model_dump(mode='json')),
            self.backend_response(200, history().model_dump(mode='json')),
        ])
        with patch.object(httpx.AsyncClient, 'get', get), patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as post:
            response = self.client.post('/credit/decide', json={'client_id': 'c-01000', 'amount_rub': 100000, 'term_months': 12})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['decision'], 'approved')
            self.assertEqual([c.args[0] for c in get.await_args_list], [main.BACKEND_URL + '/clients/c-01000', main.BACKEND_URL + '/credit-history/c-01000'])
            post.assert_not_awaited()

    def test_missing_history_is_not_treated_as_no_debt(self):
        for history_response in [self.backend_response(404, {}), self.backend_response(200, {'client_id': 'c-01000'})]:
            with patch.object(httpx.AsyncClient, 'get', AsyncMock(side_effect=[self.backend_response(200, person().model_dump(mode='json')), history_response])):
                response = self.client.post('/credit/decide', json={'client_id': 'c-01000', 'amount_rub': 100000, 'term_months': 12})
                self.assertEqual(response.status_code, 503)
                self.assertNotIn('approved', response.json())

    def test_wrong_identity_and_nonfinite_debt_fail_closed(self):
        for update in ({'client_id': 'c-01001'}, {'active_monthly_payment_rub': 'NaN'}, {'active_count': 1, 'total': 1}):
            with patch.object(httpx.AsyncClient, 'get', AsyncMock(side_effect=[self.backend_response(200, person().model_dump(mode='json')), self.backend_response(200, {**history().model_dump(mode='json'), **update})])):
                response = self.client.post('/credit/decide', json={'client_id': 'c-01000', 'amount_rub': 100000, 'term_months': 12})
                self.assertEqual(response.status_code, 503)

    def test_backend_timeout_returns_retryable_error(self):
        with patch.object(httpx.AsyncClient, 'get', AsyncMock(side_effect=httpx.ReadTimeout('private debug details'))):
            response = self.client.post('/credit/decide', json={'client_id': 'c-01000', 'amount_rub': 100000, 'term_months': 12})
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('private debug', response.text)

    def test_unknown_client_is_404(self):
        with patch.object(httpx.AsyncClient, 'get', AsyncMock(side_effect=[self.backend_response(404, {}), self.backend_response(404, {})])):
            response = self.client.post('/credit/decide', json={'client_id': 'c-99999', 'amount_rub': 100000, 'term_months': 12})
            self.assertEqual(response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
