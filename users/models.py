import random
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """Base user. Student/Teacher/Coach extend this via multi-table inheritance."""

    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        TEACHER = "teacher", "Teacher"
        COACH = "coach", "Coach"

    role = models.CharField(max_length=10, choices=Role.choices, blank=True)
    perm_address = models.CharField(max_length=255, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    gender = models.CharField(max_length=20, blank=True)
    photo = models.ImageField(upload_to="avatars/", blank=True,
                              help_text="Profile photo shown when you click your avatar.")

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    @property
    def initials(self):
        first = (self.first_name or self.username or "?")[:1]
        last = (self.last_name or "")[:1]
        return (first + last).upper()

    @property
    def role_obj(self):
        """The Student/Teacher/Coach row behind this user (or None for admins)."""
        if self.role in ("student", "teacher", "coach"):
            try:
                return getattr(self, self.role)
            except Exception:
                return None
        return None

    @property
    def personal_id(self):
        """StudentID / TeacherID / CoachID, e.g. STU-00012 (blank for admin accounts)."""
        obj = self.role_obj
        return getattr(obj, "code", "") if obj else ""


class RoleCodeMixin:
    """Gives every Student/Teacher/Coach their own readable ID
    (STU-00001, TCH-00001, CCH-00001), assigned automatically on first save."""

    CODE_PREFIX = ""
    CODE_FIELD = ""

    @property
    def code(self):
        return getattr(self, self.CODE_FIELD) or ""

    def _assign_code(self):
        if not getattr(self, self.CODE_FIELD):
            value = f"{self.CODE_PREFIX}-{self.pk:05d}"
            setattr(self, self.CODE_FIELD, value)
            type(self).objects.filter(pk=self.pk).update(**{self.CODE_FIELD: value})


class Student(RoleCodeMixin, User):
    CODE_PREFIX, CODE_FIELD = "STU", "student_code"

    class Meta:
        verbose_name = "Student"
        verbose_name_plural = "Students"

    student_code = models.CharField("Student ID", max_length=20, unique=True, null=True, blank=True,
                                    editable=False)

    registration_date = models.DateTimeField(auto_now_add=True)
    enrolled_course = models.ForeignKey(
        "catalog.Course", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="students",
    )

    def save(self, *args, **kwargs):
        self.role = User.Role.STUDENT
        super().save(*args, **kwargs)
        self._assign_code()

    def course_ids(self):
        """Every course this student can study: the enrolled course plus the
        courses of every class they joined through an invite link."""
        ids = set(self.class_groups.values_list("class_session__course_id", flat=True))
        if self.enrolled_course_id:
            ids.add(self.enrolled_course_id)
        return ids

    def enroll_in_course(self, course):
        self.enrolled_course = course
        self.save()

    def view_progress(self) -> float:
        from catalog.models import Step
        from enrollment.models import StepCompletion
        total_steps = Step.objects.filter(lesson__module__course=self.enrolled_course).count()
        if not total_steps:
            return 0.0
        # Only APPROVED steps count as done - a pending/rejected quiz or
        # practice submission doesn't count toward progress yet.
        completed = self.completed_steps.filter(status=StepCompletion.Status.APPROVED).count()
        return round(completed / total_steps * 100, 1)


class Teacher(RoleCodeMixin, User):
    CODE_PREFIX, CODE_FIELD = "TCH", "teacher_code"

    teacher_code = models.CharField("Teacher ID", max_length=20, unique=True, null=True, blank=True,
                                    editable=False)

    class Meta:
        verbose_name = "Teacher"
        verbose_name_plural = "Teachers"

    def save(self, *args, **kwargs):
        self.role = User.Role.TEACHER
        super().save(*args, **kwargs)
        self._assign_code()


class Coach(RoleCodeMixin, User):
    CODE_PREFIX, CODE_FIELD = "CCH", "coach_code"

    coach_code = models.CharField("Coach ID", max_length=20, unique=True, null=True, blank=True,
                                    editable=False)

    class Meta:
        verbose_name = "Coach"
        verbose_name_plural = "Coaches"

    def save(self, *args, **kwargs):
        self.role = User.Role.COACH
        super().save(*args, **kwargs)
        self._assign_code()


class EmailVerificationCode(models.Model):
    """A short-lived 6-digit code sent to an email address to confirm signup.

    Used by both the website (/signup/) and the API (/api/auth/signup/) so
    there is exactly one verification implementation, not two that can drift.
    """

    email = models.EmailField()
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.email} - {self.code}"

    @classmethod
    def issue(cls, email: str, ttl_minutes: int = 10) -> "EmailVerificationCode":
        # Invalidate any earlier unused codes for this email so only the newest works.
        cls.objects.filter(email=email, is_used=False).update(is_used=True)
        code = f"{random.randint(0, 999999):06d}"
        return cls.objects.create(
            email=email, code=code,
            expires_at=timezone.now() + timedelta(minutes=ttl_minutes),
        )

    def is_valid(self, code: str) -> bool:
        return (not self.is_used) and self.code == code and timezone.now() <= self.expires_at

    @classmethod
    def verify_and_consume(cls, email: str, code: str) -> bool:
        obj = cls.objects.filter(email=email, is_used=False).order_by("-created_at").first()
        if obj and obj.is_valid(code):
            obj.is_used = True
            obj.save(update_fields=["is_used"])
            return True
        return False
