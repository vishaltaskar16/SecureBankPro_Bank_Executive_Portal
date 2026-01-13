from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.admin import AdminSite
from django.urls import path, reverse
from django.template.response import TemplateResponse
from django.http import HttpResponse, HttpResponseRedirect
from django.utils import timezone
from django.db.models import Sum, Count
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.staticfiles import finders
from django.http import JsonResponse
from django.conf import settings
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
from pathlib import Path

import csv
import io
import json

from .models import BankAccountType, User, UserAddress, UserBankAccount
from transactions.models import Transaction
from transactions.constants import DEPOSIT, WITHDRAWAL


# Customize admin site headers for bank admin
admin.site.site_header = "Bank Admin Portal"
admin.site.site_title = "Bank Admin"
admin.site.index_title = "Bank Administration"
# Use custom index template (dashboard)
admin.site.index_template = 'admin/dashboard.html'


class UserBankAccountAdmin(admin.ModelAdmin):
    readonly_fields = ('account_no',)
    list_display = ('user', 'account_no', 'account_type', 'balance')


class CustomUserAdmin(DjangoUserAdmin):
    model = User
    list_display = ('email', 'is_staff', 'is_superuser', 'get_account_no', 'balance')
    search_fields = ('email',)
    ordering = ('email',)
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
    )

    def get_account_no(self, obj):
        return getattr(obj, 'account', None).account_no if getattr(obj, 'account', None) else None
    get_account_no.short_description = 'Account No'


# Admin dashboard view and helpers
@staff_member_required
def admin_dashboard(request):
    # High level metrics
    total_users = User.objects.count()
    total_transactions = Transaction.objects.count()

    total_deposits = Transaction.objects.filter(transaction_type=DEPOSIT).aggregate(total=Sum('amount'))['total'] or 0
    total_withdrawals = Transaction.objects.filter(transaction_type=WITHDRAWAL).aggregate(total=Sum('amount'))['total'] or 0

    # Transactions: support selectable range (30,90,180,365 or all)
    today = timezone.now().date()
    requested_range = request.GET.get('range', '30')
    allowed_ranges = ('30', '90', '180', '365', 'all')
    if requested_range not in allowed_ranges:
        requested_range = '30'

    if requested_range == 'all':
        # Use earliest transaction date if available, otherwise fall back to 30 days
        earliest_tx = Transaction.objects.order_by('timestamp').first()
        if earliest_tx:
            start = earliest_tx.timestamp.date()
        else:
            start = today - timezone.timedelta(days=29)
    else:
        days = int(requested_range)
        # show the requested number of days (inclusive)
        start = today - timezone.timedelta(days=days - 1)

    # Query transactions in the selected period (or all)
    tx_qs = Transaction.objects
    if requested_range != 'all':
        tx_qs = tx_qs.filter(timestamp__date__gte=start)

    tx_by_date_qs = (
        tx_qs
        .extra({'date': "date(timestamp)"})
        .values('date')
        .annotate(count=Sum('amount'))
        .order_by('date')
    )

    # Normalize into arrays for charting
    dates = []
    totals = []
    current = start
    # Build a map keyed by ISO date strings
    tx_map = {item['date']: float(item['count'] or 0) for item in tx_by_date_qs}
    while current <= today:
        dates.append(current.isoformat())
        totals.append(tx_map.get(current.isoformat(), 0))
        current += timezone.timedelta(days=1)

    # Range-based summary metrics
    range_deposits_qs = Transaction.objects.filter(transaction_type=DEPOSIT)
    range_withdrawals_qs = Transaction.objects.filter(transaction_type=WITHDRAWAL)
    if requested_range != 'all':
        range_deposits_qs = range_deposits_qs.filter(timestamp__date__range=(start, today))
        range_withdrawals_qs = range_withdrawals_qs.filter(timestamp__date__range=(start, today))

    range_total_deposits = range_deposits_qs.aggregate(total=Sum('amount'))['total'] or 0
    range_total_withdrawals = range_withdrawals_qs.aggregate(total=Sum('amount'))['total'] or 0

    # Peak and average for the period
    peak_transaction = max(totals) if totals else 0
    avg_daily_transaction = (sum(totals) / len(totals)) if totals else 0

    # Particular user selection
    user_q = None
    user_transactions = None
    user_id = request.GET.get('user_id')
    if user_id:
        try:
            user_q = User.objects.get(pk=int(user_id))
            user_transactions = Transaction.objects.filter(account=user_q.account).order_by('-timestamp')[:100]
        except Exception:
            user_q = None
            user_transactions = None

    # Additional analytics
    daily_active_users = User.objects.filter(last_login__date=today).count()
    top_accounts = list(UserBankAccount.objects.select_related('user').order_by('-balance')[:5])

    # Recent users and transactions
    recent_users = list(User.objects.order_by('-date_joined')[:5])
    recent_transactions = list(Transaction.objects.select_related('account__user').order_by('-timestamp')[:10])

    # Users without a linked account
    users_without_account_qs = User.objects.filter(account__isnull=True).order_by('-date_joined')
    users_without_account_count = users_without_account_qs.count()
    users_without_account = list(users_without_account_qs[:10])

    # Lost transactions (zero-amount)
    lost_transactions_qs = Transaction.objects.filter(amount=0).order_by('-timestamp')
    lost_transactions_count = lost_transactions_qs.count()
    lost_transactions = list(lost_transactions_qs[:10])

    # Top users by transaction count
    top_users = list(User.objects.annotate(tx_count=Count('account__transactions')).filter(tx_count__gt=0).order_by('-tx_count')[:5])

    # Asset checks for helpful admin message when local vendor assets are missing
    missing_assets = []
    bootstrap_missing = not bool(finders.find('css/bootstrap.min.css'))
    chartjs_missing = not bool(finders.find('js/chart.umd.min.js'))
    if bootstrap_missing:
        missing_assets.append('Bootstrap CSS (missing; using CDN fallback)')
    if chartjs_missing:
        missing_assets.append('Chart.js (missing; using CDN fallback)')

    context = {
        'total_users': total_users,
        'total_transactions': total_transactions,
        'total_deposits': float(total_deposits),
        'total_withdrawals': float(total_withdrawals),
        'chart_dates': json.dumps(dates),
        'chart_totals': json.dumps(totals),
        'pie_labels': json.dumps(['Deposits', 'Withdrawals']),
        'pie_data': json.dumps([float(range_total_deposits), float(range_total_withdrawals)]),
        'peak_transaction': peak_transaction,
        'avg_daily_transaction': avg_daily_transaction,
        'selected_range': requested_range,
        'daily_active_users': daily_active_users,
        'top_accounts': top_accounts,
        'user_q': user_q,
        'user_transactions': user_transactions,
        'assets_missing': missing_assets,
        'recent_users': recent_users,
        'recent_transactions': recent_transactions[:10],
        'users_without_account': users_without_account,
        'users_without_account_count': users_without_account_count,
        'lost_transactions': lost_transactions,
        'lost_transactions_count': lost_transactions_count,
        'top_users': top_users,
        'quick_links': {
            'users': reverse('admin:accounts_user_changelist'),
            'accounts': reverse('admin:accounts_userbankaccount_changelist'),
            'transactions': reverse('admin:transactions_transaction_changelist'),
        },
        # expose whether local vendor assets are present so template can use CDN fallbacks
        'bootstrap_missing': bootstrap_missing,
        'chartjs_missing': chartjs_missing,
        'assets_missing': missing_assets,
    }

    # Debug logging for live diagnosis (prints to runserver console)
    try:
        print(f"[dashboard-debug] user={getattr(request.user, 'email', 'anonymous')} range={requested_range} totals_len={len(totals)} dates_len={len(dates)} total_users={total_users} total_transactions={total_transactions} total_deposits={float(total_deposits):.2f} total_withdrawals={float(total_withdrawals):.2f}")
    except Exception:
        pass

    return TemplateResponse(request, 'admin/dashboard.html', context) 


@staff_member_required
def admin_dashboard_data(request):
    """Return JSON payload for dashboard charts and KPIs. Used by frontend fallback when template data is empty."""
    today = timezone.now().date()
    requested_range = request.GET.get('range', '30')
    allowed_ranges = ('30', '90', '180', '365', 'all')
    if requested_range not in allowed_ranges:
        requested_range = '30'

    if requested_range == 'all':
        earliest_tx = Transaction.objects.order_by('timestamp').first()
        if earliest_tx:
            start = earliest_tx.timestamp.date()
        else:
            start = today - timezone.timedelta(days=29)
    else:
        days = int(requested_range)
        start = today - timezone.timedelta(days=days - 1)

    tx_qs = Transaction.objects
    if requested_range != 'all':
        tx_qs = tx_qs.filter(timestamp__date__gte=start)

    tx_by_date_qs = (
        tx_qs
        .extra({'date': "date(timestamp)"})
        .values('date')
        .annotate(count=Sum('amount'))
        .order_by('date')
    )

    dates = []
    totals = []
    current = start
    tx_map = {item['date']: float(item['count'] or 0) for item in tx_by_date_qs}
    while current <= today:
        dates.append(current.isoformat())
        totals.append(tx_map.get(current.isoformat(), 0))
        current += timezone.timedelta(days=1)

    range_deposits_qs = Transaction.objects.filter(transaction_type=DEPOSIT)
    range_withdrawals_qs = Transaction.objects.filter(transaction_type=WITHDRAWAL)
    if requested_range != 'all':
        range_deposits_qs = range_deposits_qs.filter(timestamp__date__range=(start, today))
        range_withdrawals_qs = range_withdrawals_qs.filter(timestamp__date__range=(start, today))

    range_total_deposits = range_deposits_qs.aggregate(total=Sum('amount'))['total'] or 0
    range_total_withdrawals = range_withdrawals_qs.aggregate(total=Sum('amount'))['total'] or 0

    # Optional filter by transaction type (deposit/withdrawal)
    tx_type = request.GET.get('tx_type', 'all')
    if tx_type not in ('all', 'deposit', 'withdrawal'):
        tx_type = 'all'

    tx_filter_qs = Transaction.objects
    if requested_range != 'all':
        tx_filter_qs = tx_filter_qs.filter(timestamp__date__range=(start, today))
    if tx_type == 'deposit':
        tx_filter_qs = tx_filter_qs.filter(transaction_type=DEPOSIT)
    elif tx_type == 'withdrawal':
        tx_filter_qs = tx_filter_qs.filter(transaction_type=WITHDRAWAL)

    # Recent transactions (serialized minimally)
    recent_transactions_qs = tx_filter_qs.select_related('account__user').order_by('-timestamp')[:10]
    recent_transactions = []
    for t in recent_transactions_qs:
        recent_transactions.append({
            'id': str(t.id),
            'txid': str(t.id)[-8:].upper(),
            'timestamp': t.timestamp.isoformat(),
            'date': t.timestamp.date().isoformat(),
            'time': t.timestamp.time().strftime('%H:%M:%S'),
            'user_email': t.account.user.email if t.account and t.account.user else None,
            'amount': float(t.amount),
            'transaction_type': 'deposit' if t.transaction_type == DEPOSIT else 'withdrawal',
            'balance_after': float(t.balance_after_transaction),
        })

    # Top users by transaction count within range and filters
    top_users_qs = (User.objects
                    .annotate(tx_count=Count('account__transactions'))
                    .filter(tx_count__gt=0)
                    .order_by('-tx_count')[:5])
    top_users = []
    for u in top_users_qs:
        top_users.append({'email': u.email, 'tx_count': u.tx_count})

    payload = {
        'chart_dates': dates,
        'chart_totals': totals,
        'pie_labels': ['Deposits', 'Withdrawals'],
        'pie_data': [float(range_total_deposits), float(range_total_withdrawals)],
        'total_users': User.objects.count(),
        'total_transactions': Transaction.objects.count(),
        'total_deposits': float(Transaction.objects.filter(transaction_type=DEPOSIT).aggregate(total=Sum('amount'))['total'] or 0),
        'total_withdrawals': float(Transaction.objects.filter(transaction_type=WITHDRAWAL).aggregate(total=Sum('amount'))['total'] or 0),
        'selected_range': requested_range,
        'tx_type': tx_type,
        'recent_transactions': recent_transactions,
        'top_users': top_users,
    }
    return JsonResponse(payload)



@staff_member_required
def admin_export_dashboard_csv(request):
    """Export dashboard transactions (last 30 days by default) and KPIs as CSV."""
    # allow optional daterange param: ?start=YYYY-MM-DD&end=YYYY-MM-DD
    start = request.GET.get('start')
    end = request.GET.get('end')
    today = timezone.now().date()
    default_start = today - timezone.timedelta(days=29)

    try:
        if start:
            from datetime import date
            s = date.fromisoformat(start)
        else:
            s = default_start
        if end:
            from datetime import date
            e = date.fromisoformat(end)
        else:
            e = today
    except Exception:
        return HttpResponse('Invalid date', status=400)

    qs = Transaction.objects.filter(timestamp__date__range=(s, e)).order_by('-timestamp')

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(['Dashboard Report'])
    writer.writerow(['Date Range', f"{s} to {e}"])
    writer.writerow(['Total Users', User.objects.count()])
    total_deposits = Transaction.objects.filter(transaction_type=DEPOSIT, timestamp__date__range=(s, e)).aggregate(total=Sum('amount'))['total'] or 0
    total_withdrawals = Transaction.objects.filter(transaction_type=WITHDRAWAL, timestamp__date__range=(s, e)).aggregate(total=Sum('amount'))['total'] or 0
    writer.writerow(['Total Deposits', f"{total_deposits:.2f}"])
    writer.writerow(['Total Withdrawals', f"{total_withdrawals:.2f}"])
    writer.writerow([])
    writer.writerow(['Date', 'Time', 'Transaction ID', 'Type', 'Amount', 'Balance'])

    for t in qs:
        date_s = t.timestamp.date().isoformat()
        time_s = t.timestamp.time().strftime('%H:%M:%S')
        txid = str(t.id)[-8:].upper()
        tx_type = 'Deposit' if t.transaction_type == DEPOSIT else 'Withdrawal'
        amount = f"{t.amount:.2f}"
        if t.transaction_type == WITHDRAWAL:
            amount = f"-{amount}"
        balance = f"{t.balance_after_transaction:.2f}"
        writer.writerow([date_s, time_s, txid, tx_type, amount, balance])

    resp = HttpResponse(output.getvalue(), content_type='text/csv')
    resp['Content-Disposition'] = f'attachment; filename="dashboard_report_{s}_to_{e}.csv"'
    return resp


@staff_member_required
def admin_export_dashboard_pdf(request):
    """Export dashboard report as PDF (uses ReportLab)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    except Exception:
        resp = HttpResponse('PDF generation requires the reportlab package. Please install reportlab.', content_type='text/plain')
        resp.status_code = 500
        return resp

    today = timezone.now().date()
    start = today - timezone.timedelta(days=29)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)
    elements = []
    styles = getSampleStyleSheet()
    elements.append(Paragraph('Dashboard Report', styles['Title']))
    elements.append(Spacer(1, 12))

    total_users = User.objects.count()
    total_deposits = Transaction.objects.filter(transaction_type=DEPOSIT, timestamp__date__range=(start, today)).aggregate(total=Sum('amount'))['total'] or 0
    total_withdrawals = Transaction.objects.filter(transaction_type=WITHDRAWAL, timestamp__date__range=(start, today)).aggregate(total=Sum('amount'))['total'] or 0

    elements.append(Paragraph(f'Date Range: {start} to {today}', styles['Normal']))
    elements.append(Paragraph(f'Total Users: {total_users}', styles['Normal']))
    elements.append(Paragraph(f'Total Deposits: {total_deposits:.2f}', styles['Normal']))
    elements.append(Paragraph(f'Total Withdrawals: {total_withdrawals:.2f}', styles['Normal']))
    elements.append(Spacer(1, 12))

    data = [['Date', 'Time', 'TxID', 'Type', 'Amount', 'Balance']]
    qs = Transaction.objects.filter(timestamp__date__range=(start, today)).order_by('-timestamp')[:500]
    for t in qs:
        date_s = t.timestamp.date().isoformat()
        time_s = t.timestamp.time().strftime('%H:%M:%S')
        txid = str(t.id)[-8:].upper()
        tx_type = 'Deposit' if t.transaction_type == DEPOSIT else 'Withdrawal'
        amount = f"{t.amount:.2f}"
        if t.transaction_type == WITHDRAWAL:
            amount = f"-{amount}"
        balance = f"{t.balance_after_transaction:.2f}"
        data.append([date_s, time_s, txid, tx_type, amount, balance])

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f1f1')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (-2,0), (-1,-1), 'RIGHT'),
    ]))
    elements.append(table)

    try:
        doc.build(elements)
        pdf = buffer.getvalue()
        buffer.close()
        resp = HttpResponse(pdf, content_type='application/pdf')
        resp['Content-Disposition'] = f'attachment; filename="dashboard_report_{start}_to_{today}.pdf"'
        return resp
    except Exception as e:
        # Fallback minimal PDF when ReportLab fails at runtime (e.g., md5 OpenSSL incompat)
        fallback = b"%%PDF-1.1\n%fallback\n1 0 obj<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n4 0 obj<< /Length 44 >>\nstream\nBT\n/F1 12 Tf\n72 100 Td\n(Report generation encountered an internal error) Tj\nET\nendstream\nendobj\n5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\nxref\n0 6\n0000000000 65535 f \n0000000010 00000 n \n0000000061 00000 n \n0000000116 00000 n \n0000000231 00000 n \n0000000329 00000 n \ntrailer\n<< /Root 1 0 R /Size 6 >>\nstartxref\n430\n%%EOF"
        resp = HttpResponse(fallback, content_type='application/pdf')
        resp['Content-Disposition'] = f'attachment; filename="dashboard_report_{start}_to_{today}_fallback.pdf"'
        return resp


@staff_member_required
def admin_export_lists_csv(request):
    """Export selected dashboard lists as CSV. Use ?list=<name> where name is one of:
    recent_users, recent_transactions, users_without_account, lost_transactions, top_users
    """
    list_name = request.GET.get('list')
    output = io.StringIO()
    writer = csv.writer(output)

    if list_name == 'recent_users':
        writer.writerow(['Recent Users'])
        writer.writerow(['email', 'date_joined'])
        for u in User.objects.order_by('-date_joined')[:500]:
            writer.writerow([u.email, u.date_joined.isoformat()])

    elif list_name == 'recent_transactions':
        writer.writerow(['Recent Transactions'])
        writer.writerow(['date', 'time', 'txid', 'user_email', 'type', 'amount', 'balance'])
        qs = Transaction.objects.select_related('account__user').order_by('-timestamp')[:500]
        for t in qs:
            writer.writerow([t.timestamp.date().isoformat(), t.timestamp.time().strftime('%H:%M:%S'), str(t.id)[-8:].upper(), getattr(getattr(t, 'account', None), 'user', None).email if getattr(getattr(t, 'account', None), 'user', None) else '', 'Deposit' if t.transaction_type == DEPOSIT else 'Withdrawal', f"{t.amount:.2f}", f"{t.balance_after_transaction:.2f}"])

    elif list_name == 'users_without_account':
        writer.writerow(['Users without linked account'])
        writer.writerow(['email', 'date_joined'])
        for u in User.objects.filter(account__isnull=True).order_by('-date_joined')[:1000]:
            writer.writerow([u.email, u.date_joined.isoformat()])

    elif list_name == 'lost_transactions':
        writer.writerow(['Lost (zero-amount) Transactions'])
        writer.writerow(['date', 'time', 'txid', 'user_email', 'amount', 'balance'])
        for t in Transaction.objects.filter(amount=0).select_related('account__user').order_by('-timestamp')[:1000]:
            writer.writerow([t.timestamp.date().isoformat(), t.timestamp.time().strftime('%H:%M:%S'), str(t.id)[-8:].upper(), getattr(getattr(t, 'account', None), 'user', None).email if getattr(getattr(t, 'account', None), 'user', None) else '', f"{t.amount:.2f}", f"{t.balance_after_transaction:.2f}"])

    elif list_name == 'top_users':
        writer.writerow(['Top Users by Transaction Count'])
        writer.writerow(['email', 'tx_count'])
        qs = User.objects.annotate(tx_count=Count('account__transactions')).filter(tx_count__gt=0).order_by('-tx_count')[:500]
        for u in qs:
            writer.writerow([u.email, u.tx_count])

    else:
        return HttpResponse('Invalid list parameter', status=400)

    resp = HttpResponse(output.getvalue(), content_type='text/csv')
    resp['Content-Disposition'] = f'attachment; filename="{list_name}.csv"'
    return resp


@staff_member_required
def admin_export_csv(request):
    user_id = request.GET.get('user_id')
    if not user_id:
        return HttpResponse('user_id is required', status=400)
    try:
        user = User.objects.get(pk=int(user_id))
    except User.DoesNotExist:
        return HttpResponse('User not found', status=404)

    queryset = Transaction.objects.filter(account=user.account).order_by('-timestamp')

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(['Bank Statement'])
    writer.writerow(['User', f"{user.get_full_name() or user.email}"])
    writer.writerow(['Email', user.email])
    writer.writerow(['Account Number', user.account.account_no])
    writer.writerow([])
    writer.writerow(['Date', 'Time', 'Transaction ID', 'Type', 'Description', 'Amount', 'Balance'])

    for t in queryset:
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
    resp['Content-Disposition'] = f'attachment; filename="bank_statement_{user.email}.csv"'
    return resp


@staff_member_required
def admin_export_pdf(request):
    user_id = request.GET.get('user_id')
    if not user_id:
        return HttpResponse('user_id is required', status=400)
    try:
        user = User.objects.get(pk=int(user_id))
    except User.DoesNotExist:
        return HttpResponse('User not found', status=404)

    # PDF generation (ReportLab)
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    except Exception:
        resp = HttpResponse('PDF generation requires the reportlab package. Please install reportlab.', content_type='text/plain')
        resp.status_code = 500
        return resp

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)

    elements = []
    styles = getSampleStyleSheet()
    title = Paragraph('Bank Statement', styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 12))

    account = getattr(user, 'account', None)
    info_lines = [
        f"User: {user.get_full_name() or user.email}",
        f"Email: {user.email}",
        f"Account Number: {getattr(account, 'account_no', '')}",
    ]

    for line in info_lines:
        elements.append(Paragraph(line, styles['Normal']))
    elements.append(Spacer(1, 12))

    # Table data
    data = [['Date', 'Time', 'Transaction ID', 'Type', 'Description', 'Amount', 'Balance']]
    queryset = Transaction.objects.filter(account=user.account).order_by('-timestamp')
    for t in queryset:
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

    try:
        doc.build(elements)
        pdf = buffer.getvalue()
        buffer.close()
        resp = HttpResponse(pdf, content_type='application/pdf')
        resp['Content-Disposition'] = f'attachment; filename="bank_statement_{user.email}.pdf"'
        return resp
    except Exception as e:
        fallback = b"%%PDF-1.1\n%fallback\n1 0 obj<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n4 0 obj<< /Length 44 >>\nstream\nBT\n/F1 12 Tf\n72 100 Td\n(Report generation encountered an internal error) Tj\nET\nendstream\nendobj\n5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\nxref\n0 6\n0000000000 65535 f \n0000000010 00000 n \n0000000061 00000 n \n0000000116 00000 n \n0000000231 00000 n \n0000000329 00000 n \ntrailer\n<< /Root 1 0 R /Size 6 >>\nstartxref\n430\n%%EOF"
        resp = HttpResponse(fallback, content_type='application/pdf')
        resp['Content-Disposition'] = f'attachment; filename="bank_statement_{user.email}_fallback.pdf"'
        return resp


# Hook into admin urls: capture original and prepend our URLs

def get_admin_urls(original_get_urls):
    def wrap(view):
        return admin.site.admin_view(view)

    my_urls = [
        path('dashboard/', wrap(admin_dashboard), name='admin_dashboard'),
        path('dashboard/export_csv/', wrap(admin_export_csv), name='admin_dashboard_export_csv'),
        path('dashboard/export_pdf/', wrap(admin_export_pdf), name='admin_dashboard_export_pdf'),
        path('dashboard/export_all_csv/', wrap(admin_export_dashboard_csv), name='admin_dashboard_export_all_csv'),
        path('dashboard/export_all_pdf/', wrap(admin_export_dashboard_pdf), name='admin_dashboard_export_all_pdf'),
        path('dashboard/export_lists_csv/', wrap(admin_export_lists_csv), name='admin_dashboard_export_lists_csv'),
    ]

    def get_urls():
        return my_urls + original_get_urls()

    return get_urls

# Preserve original and replace
_original_get_urls = admin.site.get_urls
admin.site.get_urls = get_admin_urls(_original_get_urls)


admin.site.register(BankAccountType)
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass
admin.site.register(User, CustomUserAdmin)
admin.site.register(UserAddress)
admin.site.register(UserBankAccount, UserBankAccountAdmin)
