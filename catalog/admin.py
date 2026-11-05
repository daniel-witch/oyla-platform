from django.contrib import admin
from .models import Course, Module, Lesson, Step, Resource


class ModuleInline(admin.TabularInline):
    model = Module
    extra = 1


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1


class StepInline(admin.StackedInline):
    model = Step
    extra = 1
    fields = ("title", "step_type", "order", "body", "link", "video_file")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("name", "number")
    search_fields = ("name", "number")
    inlines = [ModuleInline]


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ("name", "course", "order")
    inlines = [LessonInline]


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("name", "module", "order")
    inlines = [StepInline]


@admin.register(Step)
class StepAdmin(admin.ModelAdmin):
    list_display = ("display_name", "lesson", "step_type", "order", "video_source")
    list_filter = ("step_type",)
    search_fields = ("title", "body")
    fields = ("lesson", "title", "step_type", "order", "body", "link", "video_file")

    @admin.display(description="Video")
    def video_source(self, obj):
        if obj.video_file:
            return "Uploaded file"
        if obj.youtube_id:
            return "YouTube (plays in app)"
        return "—"


admin.site.register(Resource)
