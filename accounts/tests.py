from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.urls import reverse
from unittest.mock import patch
from .models import UserBankAccount, BankAccountType
from transactions.constants import DEPOSIT, WITHDRAWAL


User = get_user_model()


class AccountTests(TestCase):
    def test_account_number_is_immutable(self):
        user = User.objects.create_user(email='a@test.com', password='testpass')
        bt = BankAccountType.objects.create(name='Basic', maximum_withdrawal_amount=1000, annual_interest_rate=1.0, interest_calculation_per_year=12)
        account = UserBankAccount.objects.create(user=user, account_type=bt, account_no=12345, gender='M')

        # Changing account_no should raise ValidationError on save
        account.account_no = 99999
        with self.assertRaises(ValidationError):
            account.save()


class StaffLoginTests(TestCase):
    def test_staff_login_redirects_to_admin_index(self):
        user = User.objects.create_user(email='staff@test.com', password='testpass', is_staff=True)
        # Use the login view to post credentials
        resp = self.client.post(reverse('accounts:user_login'), {
            'username': 'staff@test.com',
            'password': 'testpass'
        })
        # After login, staff should be redirected to the admin index
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('admin:index'), resp['Location'])

    def test_admin_dashboard_accessible_to_staff(self):
        staff = User.objects.create_user(email='adminuser@test.com', password='testpass', is_staff=True)
        # create some users so KPI is non-zero
        User.objects.create_user(email='u1@test.com', password='testpass')
        User.objects.create_user(email='u2@test.com', password='testpass')
        self.client.login(email='adminuser@test.com', password='testpass')
        resp = self.client.get(reverse('admin:admin_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Bank Admin Dashboard')
        # Ensure KPIs render numeric values
        self.assertContains(resp, 'Total Users')
        self.assertContains(resp, '2')

    def test_nav_sidebar_removed(self):
        staff = User.objects.create_user(email='nohover@test.com', password='testpass', is_staff=True)
        self.client.login(email='nohover@test.com', password='testpass')
        resp = self.client.get(reverse('admin:admin_dashboard'))
        self.assertEqual(resp.status_code, 200)
        # nav sidebar container should not be rendered
        self.assertNotContains(resp, 'id="nav-sidebar"')
        # The dashboard should still show quick links (our replacements)
        self.assertContains(resp, 'Accounts')
        self.assertContains(resp, 'Transactions')

    def test_dashboard_export_csv_and_pdf(self):
        staff = User.objects.create_user(email='dashadmin@test.com', password='testpass', is_staff=True)
        bt = BankAccountType.objects.create(name='BasicX', maximum_withdrawal_amount=1000, annual_interest_rate=1.0, interest_calculation_per_year=12)
        u = User.objects.create_user(email='cust3@test.com', password='testpass')
        acc = UserBankAccount.objects.create(user=u, account_type=bt, account_no=44444, gender='M', balance=300)
        from transactions.models import Transaction
        Transaction.objects.create(account=acc, amount=20, transaction_type=1, balance_after_transaction=320)

        self.client.login(email='dashadmin@test.com', password='testpass')
        resp_csv = self.client.get(reverse('admin:admin_dashboard_export_all_csv'))
        self.assertEqual(resp_csv.status_code, 200)
        self.assertEqual(resp_csv['Content-Type'], 'text/csv')

        try:
            import reportlab  # noqa
        except Exception:
            return

        resp_pdf = self.client.get(reverse('admin:admin_dashboard_export_all_pdf'))
        self.assertEqual(resp_pdf.status_code, 200)
        self.assertEqual(resp_pdf['Content-Type'], 'application/pdf')

    def test_dashboard_shows_asset_warning_when_missing(self):
        staff = User.objects.create_user(email='assetadmin@test.com', password='testpass', is_staff=True)
        self.client.login(email='assetadmin@test.com', password='testpass')
        # Simulate missing static assets
        with patch('django.contrib.staticfiles.finders.find', return_value=None):
            resp = self.client.get(reverse('admin:admin_dashboard'))
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, 'Missing assets')
            self.assertContains(resp, 'fetch_bootstrap')
            self.assertContains(resp, 'fetch_chartjs')

    def test_dashboard_lists_and_exports(self):
        # Setup data
        staff = User.objects.create_user(email='listadmin@test.com', password='testpass', is_staff=True)
        # create some users
        u1 = User.objects.create_user(email='ru1@test.com', password='testpass')
        u2 = User.objects.create_user(email='ru2@test.com', password='testpass')
        # create an account and some transactions
        bt = BankAccountType.objects.create(name='BasicZ', maximum_withdrawal_amount=1000, annual_interest_rate=1.0, interest_calculation_per_year=12)
        acc = UserBankAccount.objects.create(user=u1, account_type=bt, account_no=55555, gender='M', balance=100)
        from transactions.models import Transaction
        Transaction.objects.create(account=acc, amount=0, transaction_type=WITHDRAWAL, balance_after_transaction=100)
        Transaction.objects.create(account=acc, amount=50, transaction_type=DEPOSIT, balance_after_transaction=150)

        self.client.login(email='listadmin@test.com', password='testpass')
        resp = self.client.get(reverse('admin:admin_dashboard'))
        self.assertEqual(resp.status_code, 200)
        # Ensure recent users and transactions show up
        self.assertContains(resp, 'Recent Users')
        self.assertContains(resp, 'ru1@test.com')
        self.assertContains(resp, 'Recent Transactions')
        # Ensure lost transactions count and listing present
        self.assertContains(resp, 'Lost Transactions')
        self.assertContains(resp, '0.00')

        # CSV exports
        resp_csv = self.client.get(reverse('admin:admin_dashboard_export_lists_csv') + '?list=recent_users')
        self.assertEqual(resp_csv.status_code, 200)
        self.assertEqual(resp_csv['Content-Type'], 'text/csv')
        self.assertIn('ru1@test.com', resp_csv.content.decode('utf-8'))

        resp_csv2 = self.client.get(reverse('admin:admin_dashboard_export_lists_csv') + '?list=lost_transactions')
        self.assertEqual(resp_csv2.status_code, 200)
        self.assertEqual(resp_csv2['Content-Type'], 'text/csv')
        self.assertIn('0.00', resp_csv2.content.decode('utf-8'))

    def test_admin_logout_redirects_to_home(self):
        staff = User.objects.create_user(email='adminuser2@test.com', password='testpass', is_staff=True)
        self.client.login(email='adminuser2@test.com', password='testpass')
        # Post to admin logout to perform logout
        resp = self.client.post(reverse('admin:logout'), follow=True)
        # After logout, we should end up on site home
        # Followed redirects should include the root URL
        last_url = resp.request['PATH_INFO']
        self.assertEqual(last_url, '/')

    def test_admin_export_csv_for_user(self):
        # Create a user with account and some transactions
        bt = BankAccountType.objects.create(name='Basic2', maximum_withdrawal_amount=1000, annual_interest_rate=1.0, interest_calculation_per_year=12)
        u = User.objects.create_user(email='cust@test.com', password='testpass')
        acc = UserBankAccount.objects.create(user=u, account_type=bt, account_no=22222, gender='M', balance=100)
        # create a transaction
        from transactions.models import Transaction
        t = Transaction.objects.create(account=acc, amount=50, transaction_type=1, balance_after_transaction=150)

        staff = User.objects.create_user(email='adminx@test.com', password='testpass', is_staff=True)
        self.client.login(email='adminx@test.com', password='testpass')
        resp = self.client.get(reverse('admin:admin_dashboard_export_csv') + f'?user_id={u.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv')
        self.assertIn('bank_statement', resp['Content-Disposition'])

    def test_admin_export_pdf_for_user(self):
        try:
            import reportlab  # noqa
        except Exception:
            return

        bt = BankAccountType.objects.create(name='Basic3', maximum_withdrawal_amount=1000, annual_interest_rate=1.0, interest_calculation_per_year=12)
        u = User.objects.create_user(email='cust2@test.com', password='testpass')
        acc = UserBankAccount.objects.create(user=u, account_type=bt, account_no=33333, gender='M', balance=200)
        # create a transaction
        from transactions.models import Transaction
        t = Transaction.objects.create(account=acc, amount=75, transaction_type=1, balance_after_transaction=275)

        staff = User.objects.create_user(email='adminy@test.com', password='testpass', is_staff=True)
        self.client.login(email='adminy@test.com', password='testpass')
        resp = self.client.get(reverse('admin:admin_dashboard_export_pdf') + f'?user_id={u.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertIn('bank_statement', resp['Content-Disposition'])


class AdminDashboardApiTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(email='apistaff@test.com', password='testpass', is_staff=True)
        bt = BankAccountType.objects.create(name='API', maximum_withdrawal_amount=1000, annual_interest_rate=1.0, interest_calculation_per_year=12)
        self.u = User.objects.create_user(email='apiuser@test.com', password='testpass')
        self.acc = UserBankAccount.objects.create(user=self.u, account_type=bt, account_no=99999, gender='M', balance=1000)
        from transactions.models import Transaction
        # create deposit and withdrawal
        Transaction.objects.create(account=self.acc, amount=200, transaction_type=1, balance_after_transaction=1200)
        Transaction.objects.create(account=self.acc, amount=50, transaction_type=2, balance_after_transaction=1150)
        self.client.login(email='apistaff@test.com', password='testpass')

    def test_dashboard_api_returns_payload(self):
        resp = self.client.get(reverse('admin-dashboard-data'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('chart_dates', data)
        self.assertIn('chart_totals', data)
        self.assertIn('pie_labels', data)
        self.assertIn('pie_data', data)
        self.assertIn('total_users', data)
        self.assertIn('recent_transactions', data)
        self.assertIn('top_users', data)

    def test_dashboard_api_filters_tx_type(self):
        resp = self.client.get(reverse('admin-dashboard-data') + '?tx_type=deposit')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(all(t['transaction_type'] == 'deposit' for t in data.get('recent_transactions', [])))



