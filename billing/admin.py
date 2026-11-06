from django.contrib import admin

from .models import FinancialCategory, FinancialEntry, FinancialEvent, Invoice, Payment, Plan

admin.site.register(Plan)


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("student", "competence", "amount", "due_date", "status", "paid_at")
    list_filter = ("status", "competence")
    search_fields = ("student__user__first_name", "student__user__email")
    inlines = [PaymentInline]
    date_hierarchy = "competence"


@admin.register(FinancialCategory)
class FinancialCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("name",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyFinanceAdmin(admin.ModelAdmin):
    """Toda escrita passa pela tela financeira e seus serviços auditados."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FinancialEntry)
class FinancialEntryAdmin(ReadOnlyFinanceAdmin):
    list_display = ("description", "kind", "category", "amount", "due_date", "status", "settled_at")
    list_filter = ("kind", "status", "category")
    search_fields = ("description", "counterparty")
    date_hierarchy = "due_date"


@admin.register(FinancialEvent)
class FinancialEventAdmin(ReadOnlyFinanceAdmin):
    list_display = ("entry", "action", "actor", "created_at")
    list_filter = ("action",)
    date_hierarchy = "created_at"
