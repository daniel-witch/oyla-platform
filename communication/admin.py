from django.contrib import admin

from .models import Announcement, Message


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "author", "is_pinned", "created_at")
    list_filter = ("category", "is_pinned")
    search_fields = ("title", "body")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "sender", "recipient", "created_at", "read_at", "emailed")
    search_fields = ("subject", "body", "sender__username", "recipient__username")
    autocomplete_fields = ["sender", "recipient"]
