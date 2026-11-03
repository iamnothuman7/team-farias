from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from .models import Guardian, Student, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "full_name", "role", "phone", "is_active")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("email", "first_name", "last_name", "phone")
    ordering = ("first_name",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Dados pessoais", {"fields": ("first_name", "last_name", "phone", "birth_date")}),
        ("Permissões", {"fields": ("role", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Datas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"fields": ("email", "first_name", "last_name", "role", "password1", "password2")}),
    )


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("display_name", "full_name", "level", "status", "guardian", "points_badge")
    list_filter = ("status", "level")
    search_fields = ("user__first_name", "user__last_name", "user__email", "nickname")
    autocomplete_fields = ("user", "guardian")

    @admin.display(description="pontos")
    def points_badge(self, obj):
        return format_html("<b>{}</b>", obj.total_points)


@admin.register(Guardian)
class GuardianAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "students_count")
    search_fields = ("name", "phone", "email")

    @admin.display(description="alunos")
    def students_count(self, obj):
        return obj.students.count()
