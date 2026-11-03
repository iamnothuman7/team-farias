from django.contrib import admin

from .models import Invoice, Payment, Plan

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
