from django.contrib import admin
from .models import ClassSession, ClassInvite, Group, StepCompletion, Feedback, Meetup


class GroupInline(admin.TabularInline):
    """Lets you add several students (each paired with a coach) to a
    Class Session on one page, instead of visiting Groups > Add once
    per student. 'extra' rows are blank and ready to fill in; adding
    more students later is just re-opening this same Class Session
    page - the existing rows stay, and you get fresh blank ones again."""
    model = Group
    extra = 5
    autocomplete_fields = ["student", "coach"]


@admin.register(ClassSession)
class ClassSessionAdmin(admin.ModelAdmin):
    list_display = ("name", "course", "teacher", "start_date", "meeting_link")
    search_fields = ("name", "course__name", "teacher__username")
    autocomplete_fields = ["course", "teacher"]
    fields = ("course", "teacher", "name", "description", "start_date", "finish_date", "meeting_link")
    inlines = [GroupInline]


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "class_session", "student", "coach")
    list_filter = ("class_session",)
    autocomplete_fields = ["class_session", "student", "coach"]


@admin.register(StepCompletion)
class StepCompletionAdmin(admin.ModelAdmin):
    list_display = ("student", "step", "completed_at")
    autocomplete_fields = ["student", "step"]


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("teacher", "student", "direction", "created_at")
    list_filter = ("direction",)
    autocomplete_fields = ["teacher", "student"]


@admin.register(Meetup)
class MeetupAdmin(admin.ModelAdmin):
    list_display = ("student", "coach", "status", "scheduled_time", "meeting_link")
    list_filter = ("status",)
    autocomplete_fields = ["student", "coach"]
    fields = ("student", "coach", "status", "scheduled_time", "meeting_link", "notes")


@admin.register(ClassInvite)
class ClassInviteAdmin(admin.ModelAdmin):
    list_display = ("class_session", "created_by", "coach", "token", "uses", "max_uses", "expires_at", "is_active")
    list_filter = ("is_active",)
    readonly_fields = ("token", "uses", "created_at")
    autocomplete_fields = ["class_session", "coach"]
