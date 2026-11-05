from django.contrib import admin

from .models import JsonRecord


@admin.register(JsonRecord)
class JsonRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "category", "created_by", "created_at", "updated_at")
    list_filter = ("category", "created_at")
    search_fields = ("title", "category", "created_by__username", "teacher_comment")
    readonly_fields = ("created_at", "updated_at")
