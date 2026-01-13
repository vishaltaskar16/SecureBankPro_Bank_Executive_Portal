from django.contrib import admin

from transactions.models import Transaction


class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'account', 'transaction_type', 'amount', 'balance_after_transaction', 'timestamp')
    list_filter = ('transaction_type', 'timestamp')
    search_fields = ('account__account_no', 'account__user__email')


admin.site.register(Transaction, TransactionAdmin)
