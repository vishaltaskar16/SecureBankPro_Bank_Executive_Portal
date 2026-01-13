from dateutil.relativedelta import relativedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView
from django.http import HttpResponse
from django.shortcuts import render, redirect

from transactions.constants import DEPOSIT, WITHDRAWAL
from transactions.forms import (
    DepositForm,
    TransactionDateRangeForm,
    WithdrawForm,
)
from transactions.models import Transaction

import csv
import io

# PDF generation (ReportLab)
try:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False


class TransactionRepostView(LoginRequiredMixin, ListView):
    template_name = 'transactions/transaction_report.html'
    model = Transaction
    form_data = {}

    def dispatch(self, request, *args, **kwargs):
        """Ensure the logged in user has a bank account before proceeding."""
        if not hasattr(request.user, 'account'):
            messages.warning(request, 'You do not have a bank account. Please create one from your profile.')
            return redirect('accounts:profile_edit')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        form = TransactionDateRangeForm(request.GET or None)
        if form.is_valid():
            self.form_data = form.cleaned_data

        # Handle exports
        fmt = request.GET.get('format')
        if fmt in ('csv', 'pdf', 'print'):
            # Build the queryset early
            queryset = self.get_queryset()

            if fmt == 'csv':
                return self._export_csv(queryset)
            if fmt == 'pdf':
                return self._export_pdf(queryset)
            if fmt == 'print':
                # Render a print-friendly page
                context = self.get_context_data(object_list=queryset)
                context['print_mode'] = True
                return render(request, 'transactions/transaction_report_print.html', context)

        return super().get(request, *args, **kwargs)

    def _export_csv(self, queryset):
        """Return a CSV HttpResponse containing transactions and user/account info."""
        user = self.request.user
        account = getattr(user, 'account', None)
        if not account:
            messages.warning(self.request, 'You do not have a bank account. Cannot export statement.')
            return redirect('accounts:profile_edit')

        output = io.StringIO()
        writer = csv.writer(output)

        # Header metadata
        writer.writerow(['Bank Statement'])
        writer.writerow(['User', f"{user.get_full_name() or user.email}"])
        writer.writerow(['Email', user.email])
        writer.writerow(['Account Number', account.account_no])
        if self.form_data.get('daterange'):
            writer.writerow(['Date Range', f"{self.form_data['daterange'][0]} to {self.form_data['daterange'][1]}"])
        writer.writerow([])

        # Column headers
        writer.writerow(['Date', 'Time', 'Transaction ID', 'Type', 'Description', 'Amount', 'Balance'])

        for t in queryset.order_by('-timestamp'):
            date = t.timestamp.date().isoformat()
            time = t.timestamp.time().strftime('%H:%M:%S')
            txid = str(t.id)[-8:].upper()
            tx_type = 'Deposit' if t.transaction_type == DEPOSIT else 'Withdrawal'
            description = 'Money deposited to account' if t.transaction_type == DEPOSIT else 'Money withdrawn from account'
            amount = f"{t.amount:.2f}"
            if t.transaction_type == WITHDRAWAL:
                amount = f"-{amount}"
            balance = f"{t.balance_after_transaction:.2f}"
            writer.writerow([date, time, txid, tx_type, description, amount, balance])

        resp = HttpResponse(output.getvalue(), content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="bank_statement.csv"'
        return resp

    def _export_pdf(self, queryset):
        """Return a PDF HttpResponse containing transactions and user/account info using ReportLab."""
        if not REPORTLAB_AVAILABLE:
            resp = HttpResponse('PDF generation requires the reportlab package. Please install reportlab.', content_type='text/plain')
            resp.status_code = 500
            return resp

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)

        elements = []
        styles = getSampleStyleSheet()
        title = Paragraph('Bank Statement', styles['Title'])
        elements.append(title)
        elements.append(Spacer(1, 12))

        user = self.request.user
        account = getattr(user, 'account', None)
        if not account:
            messages.warning(self.request, 'You do not have a bank account. Cannot generate PDF.')
            return redirect('accounts:profile_edit')

        info_lines = [
            f"User: {user.get_full_name() or user.email}",
            f"Email: {user.email}",
            f"Account Number: {account.account_no}",
        ]
        if self.form_data.get('daterange'):
            info_lines.append(f"Date Range: {self.form_data['daterange'][0]} to {self.form_data['daterange'][1]}")

        for line in info_lines:
            elements.append(Paragraph(line, styles['Normal']))
        elements.append(Spacer(1, 12))

        # Table data
        data = [['Date', 'Time', 'Transaction ID', 'Type', 'Description', 'Amount', 'Balance']]
        for t in queryset.order_by('-timestamp'):
            date = t.timestamp.date().isoformat()
            time = t.timestamp.time().strftime('%H:%M:%S')
            txid = str(t.id)[-8:].upper()
            tx_type = 'Deposit' if t.transaction_type == DEPOSIT else 'Withdrawal'
            description = 'Money deposited to account' if t.transaction_type == DEPOSIT else 'Money withdrawn from account'
            amount = f"{t.amount:.2f}"
            if t.transaction_type == WITHDRAWAL:
                amount = f"-{amount}"
            balance = f"{t.balance_after_transaction:.2f}"
            data.append([date, time, txid, tx_type, description, amount, balance])

        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f1f1')),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('ALIGN', (-2,0), (-1,-1), 'RIGHT'),
        ]))

        elements.append(table)

        doc.build(elements)
        pdf = buffer.getvalue()
        buffer.close()

        resp = HttpResponse(pdf, content_type='application/pdf')
        resp['Content-Disposition'] = 'attachment; filename="bank_statement.pdf"'
        return resp

    def get_queryset(self):
        # Be defensive: return an empty queryset if there's no account
        account = getattr(self.request.user, 'account', None)
        if not account:
            return self.model.objects.none()

        queryset = super().get_queryset().filter(
            account=account
        )

        daterange = self.form_data.get("daterange")

        if daterange:
            queryset = queryset.filter(timestamp__date__range=daterange)

        return queryset.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.get_queryset()

        # Totals for the filtered queryset
        from django.db.models import Sum

        total_deposits = queryset.filter(transaction_type=DEPOSIT).aggregate(total=Sum('amount'))['total'] or 0
        total_withdrawals = queryset.filter(transaction_type=WITHDRAWAL).aggregate(total=Sum('amount'))['total'] or 0
        net_flow = (total_deposits - total_withdrawals)

        context.update({
            'account': self.request.user.account,
            'form': TransactionDateRangeForm(self.request.GET or None),
            'total_deposits': total_deposits,
            'total_withdrawals': total_withdrawals,
            'net_flow': net_flow,
        })

        return context


class TransactionCreateMixin(LoginRequiredMixin, CreateView):
    template_name = 'transactions/transaction_form.html'
    model = Transaction
    title = ''
    success_url = reverse_lazy('transactions:transaction_report')

    def dispatch(self, request, *args, **kwargs):
        if not hasattr(request.user, 'account'):
            messages.warning(request, 'You do not have a bank account. Please create one to perform transactions.')
            return redirect('accounts:profile_edit')
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({
            'account': self.request.user.account
        })
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'title': self.title,
            'account': self.request.user.account,
        })

        return context


class DepositMoneyView(TransactionCreateMixin):
    form_class = DepositForm
    title = 'Deposit Money to Your Account'

    def get_initial(self):
        initial = {'transaction_type': DEPOSIT}
        return initial

    def form_valid(self, form):
        amount = form.cleaned_data.get('amount')
        account = getattr(self.request.user, 'account', None)
        if not account:
            messages.warning(self.request, 'You do not have a bank account. Cannot deposit.')
            return redirect('accounts:profile_edit')

        if not account.initial_deposit_date:
            now = timezone.now()
            next_interest_month = int(
                12 / account.account_type.interest_calculation_per_year
            )
            account.initial_deposit_date = now
            account.interest_start_date = (
                now + relativedelta(
                    months=+next_interest_month
                )
            )

        account.balance += amount
        account.save(
            update_fields=[
                'initial_deposit_date',
                'balance',
                'interest_start_date'
            ]
        )

        messages.success(
            self.request,
            f'{"{:,.2f}".format(float(amount))}$ was deposited to your account successfully'
        )

        return super().form_valid(form)


class WithdrawMoneyView(TransactionCreateMixin):
    form_class = WithdrawForm
    title = 'Withdraw Money from Your Account'

    def get_initial(self):
        initial = {'transaction_type': WITHDRAWAL}
        return initial

    def form_valid(self, form):
        amount = form.cleaned_data.get('amount')

        account = getattr(self.request.user, 'account', None)
        if not account:
            messages.warning(self.request, 'You do not have a bank account. Cannot withdraw.')
            return redirect('accounts:profile_edit')

        account.balance -= form.cleaned_data.get('amount')
        account.save(update_fields=['balance'])

        messages.success(
            self.request,
            f'Successfully withdrawn {"{:,.2f}".format(float(amount))}$ from your account'
        )

        return super().form_valid(form)
