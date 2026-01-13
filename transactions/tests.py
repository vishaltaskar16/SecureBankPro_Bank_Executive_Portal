from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from accounts.models import BankAccountType, UserBankAccount
from transactions.models import Transaction
from transactions.constants import DEPOSIT, WITHDRAWAL


User = get_user_model()


class TransactionReportTotalsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='u@test.com', password='testpass')
        self.bt = BankAccountType.objects.create(name='Basic', maximum_withdrawal_amount=1000, annual_interest_rate=1.0, interest_calculation_per_year=12)
        self.account = UserBankAccount.objects.create(user=self.user, account_type=self.bt, account_no=11111, gender='M')

        # Create transactions
        Transaction.objects.create(account=self.account, amount=100, balance_after_transaction=100, transaction_type=DEPOSIT)
        Transaction.objects.create(account=self.account, amount=50, balance_after_transaction=50, transaction_type=WITHDRAWAL)
        Transaction.objects.create(account=self.account, amount=25, balance_after_transaction=75, transaction_type=DEPOSIT)

    def test_totals_in_context(self):
        self.client.login(email='u@test.com', password='testpass')
        resp = self.client.get(reverse('transactions:transaction_report'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('total_deposits', resp.context)
        self.assertIn('total_withdrawals', resp.context)
        self.assertEqual(float(resp.context['total_deposits']), 125.0)
        self.assertEqual(float(resp.context['total_withdrawals']), 50.0)
        self.assertEqual(float(resp.context['net_flow']), 75.0)

    def test_csv_export_includes_user_and_transactions(self):
        self.client.login(email='u@test.com', password='testpass')
        resp = self.client.get(reverse('transactions:transaction_report') + '?format=csv')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv')
        content = resp.content.decode('utf-8')
        self.assertIn('Bank Statement', content)
        self.assertIn('User', content)
        self.assertIn('Transaction ID', content)

    def test_pdf_export_returns_pdf_when_reportlab_available(self):
        # Only run if reportlab is installed
        try:
            import reportlab  # noqa
        except Exception:
            return

        self.client.login(email='u@test.com', password='testpass')
        resp = self.client.get(reverse('transactions:transaction_report') + '?format=pdf')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertIn('attachment; filename="bank_statement.pdf"', resp['Content-Disposition'])


class MissingAccountTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='nouseracct@test.com', password='testpass')

    def test_report_redirects_if_user_has_no_account(self):
        self.client.login(email='nouseracct@test.com', password='testpass')
        resp = self.client.get(reverse('transactions:transaction_report'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('accounts:profile_edit'), resp['Location'])
