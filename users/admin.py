from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import User, Student, Teacher, Coach, EmailVerificationCode

PROFILE_FIELDS = ("photo", "phone_number", "birth_date", "gender", "perm_address")


def _role_forms(model):
    class ChangeForm(UserChangeForm):
        class Meta(UserChangeForm.Meta):
            pass
    ChangeForm.Meta.model = model

    class CreationForm(UserCreationForm):
        class Meta(UserCreationForm.Meta):
            fields = ("username", "email", "first_name", "last_name")
    CreationForm.Meta.model = model
    return ChangeForm, CreationForm


class RoleUserAdmin(UserAdmin):
    """Student/Teacher/Coach admin built on Django's UserAdmin, so the admin
    panel has the standard secure password tools: a hashed password on
    'Add', and a 'Reset password' form (…/password/) on every user page.
    Users can also change their own password from their panel (Change password)."""

    code_field = None
    list_display = ("username", "first_name", "last_name", "email")
    search_fields = ("username", "first_name", "last_name", "email")
    add_fieldsets = (
        (None, {"classes": ("wide",),
                "fields": ("username", "email", "first_name", "last_name", "password1", "password2")}),
    )

    def get_list_display(self, request):
        return ((self.code_field,) if self.code_field else ()) + tuple(self.list_display)

    def get_search_fields(self, request):
        return ((self.code_field,) if self.code_field else ()) + tuple(self.search_fields)

    def get_readonly_fields(self, request, obj=None):
        return ((self.code_field,) if self.code_field and obj else ()) + ("last_login", "date_joined")

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return self.add_fieldsets
        personal = ("first_name", "last_name", "email") + PROFILE_FIELDS
        extra = self.extra_fields()
        return (
            (None, {"fields": ((self.code_field,) if self.code_field else ()) + ("username", "password")}),
            ("Personal info", {"fields": personal}),
            *((("Course", {"fields": extra}),) if extra else ()),
            ("Status", {"fields": ("is_active", "last_login", "date_joined")}),
        )

    def extra_fields(self):
        return ()


@admin.register(Student)
class StudentAdmin(RoleUserAdmin):
    code_field = "student_code"
    list_display = RoleUserAdmin.list_display + ("enrolled_course",)
    form, add_form = _role_forms(Student)

    def extra_fields(self):
        return ("enrolled_course",)


@admin.register(Teacher)
class TeacherAdmin(RoleUserAdmin):
    code_field = "teacher_code"
    form, add_form = _role_forms(Teacher)


@admin.register(Coach)
class CoachAdmin(RoleUserAdmin):
    code_field = "coach_code"
    form, add_form = _role_forms(Coach)


class PlainUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Profile", {"fields": ("role",) + PROFILE_FIELDS}),)


admin.site.register(User, PlainUserAdmin)


@admin.register(EmailVerificationCode)
class EmailVerificationCodeAdmin(admin.ModelAdmin):
    """Read-only visibility into issued codes - handy for a live defense demo
    (shows the code without needing to look at the server console)."""
    list_display = ("email", "code", "created_at", "expires_at", "is_used")
    list_filter = ("is_used",)
    search_fields = ("email",)
    readonly_fields = ("email", "code", "created_at", "expires_at", "is_used")

    def has_add_permission(self, request):
        return False
