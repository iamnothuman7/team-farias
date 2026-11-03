from django.contrib import admin

from .models import Announcement, Attendance, ClassGroup, Enrollment, PointEntry, PointRule, ScheduleSlot, Session, Venue

admin.site.site_header = "Team Farias — Administração"
admin.site.site_title = "Team Farias"
admin.site.index_title = "Gestão da escolinha"


class ScheduleSlotInline(admin.TabularInline):
    model = ScheduleSlot
    extra = 0


@admin.register(ClassGroup)
class ClassGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "level", "professor", "occupied", "capacity", "is_active")
    list_filter = ("category", "level", "is_active")
    search_fields = ("name",)
    inlines = [ScheduleSlotInline]


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "class_group", "status", "theme")
    list_filter = ("status", "class_group")
    date_hierarchy = "date"
    search_fields = ("theme",)


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("student", "session", "status")
    list_filter = ("status",)
    autocomplete_fields = ("student", "session")


@admin.register(PointEntry)
class PointEntryAdmin(admin.ModelAdmin):
    list_display = ("student", "points", "reason", "source", "created_at")
    list_filter = ("source",)
    search_fields = ("reason", "student__user__first_name")
    autocomplete_fields = ("student",)


@admin.register(PointRule)
class PointRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "points", "is_active")


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "audience", "is_published", "is_pinned", "published_at")
    list_filter = ("kind", "audience", "is_published")
    search_fields = ("title", "body")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "class_group", "plan", "status", "enrolled_at")
    list_filter = ("status", "class_group")
    search_fields = ("student__user__first_name", "student__user__email")


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "is_active")
    search_fields = ("name",)
