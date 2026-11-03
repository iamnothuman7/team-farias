
from django.contrib import admin
from .models import SiteConfiguration


@admin.register(SiteConfiguration)
class SiteConfigurationAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return super().has_add_permission(request) and not SiteConfiguration.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
