from django.contrib.auth import password_validation
from rest_framework import serializers

from users.models import User, Student, Teacher, Coach
from catalog.models import Course, Module, Lesson, Step, Resource
from enrollment.models import ClassSession, ClassInvite, Group, StepCompletion, Feedback, Meetup
from communication.models import Announcement, Message


# ---- Users ----

class UserSerializer(serializers.ModelSerializer):
    personal_id = serializers.CharField(read_only=True, help_text="StudentID / TeacherID / CoachID")
    photo = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = User
        fields = [
            "id", "personal_id", "username", "first_name", "last_name", "email", "role", "access_level",
            "perm_address", "birth_date", "phone_number", "gender", "photo",
        ]
        read_only_fields = ["id", "role", "username"]

    access_level = serializers.SerializerMethodField(help_text="guest / member / administrator")

    def get_access_level(self, obj):
        from .permissions import access_level
        return access_level(obj)


class UserAdminSerializer(serializers.ModelSerializer):
    """/api/users/: every account. Administrators create/change/delete; members read.
    `access_level` is guest / member / administrator."""
    personal_id = serializers.CharField(read_only=True)
    access_level = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ["id", "personal_id", "username", "password", "first_name", "last_name", "email",
                  "role", "access_level", "is_staff", "is_active", "date_joined"]
        read_only_fields = ["id", "role", "date_joined"]
        extra_kwargs = {"is_staff": {"required": False}, "is_active": {"required": False}}

    def get_access_level(self, obj):
        from .permissions import access_level
        return access_level(obj)

    def validate_password(self, value):
        password_validation.validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class RoleUserSerializer(serializers.ModelSerializer):
    """Base for Student/Teacher/Coach: writable password, never returned."""

    password = serializers.CharField(write_only=True, required=False, style={"input_type": "password"})

    def validate_password(self, value):
        password_validation.validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        instance = self.Meta.model(**validated_data)
        if password:
            instance.set_password(password)
        else:
            instance.set_unusable_password()
        instance.save()
        return instance

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class StudentSerializer(RoleUserSerializer):
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            "id", "student_code", "username", "password", "first_name", "last_name", "email",
            "perm_address", "birth_date", "phone_number", "gender", "photo",
            "registration_date", "enrolled_course", "progress",
        ]
        read_only_fields = ["id", "student_code", "registration_date"]

    def get_progress(self, obj):
        return obj.view_progress()


class TeacherSerializer(RoleUserSerializer):
    class Meta:
        model = Teacher
        fields = [
            "id", "teacher_code", "username", "password", "first_name", "last_name", "email",
            "perm_address", "birth_date", "phone_number", "gender", "photo",
        ]
        read_only_fields = ["id", "teacher_code"]


class CoachSerializer(RoleUserSerializer):
    class Meta:
        model = Coach
        fields = [
            "id", "coach_code", "username", "password", "first_name", "last_name", "email",
            "perm_address", "birth_date", "phone_number", "gender", "photo",
        ]
        read_only_fields = ["id", "coach_code"]


# ---- Catalog ----

class ResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resource
        fields = ["id", "step", "resource_type", "body", "link"]

    def to_representation(self, obj):
        data = super().to_representation(obj)
        # A multiple-choice step keeps its answer key here ("Answer key: 1-A, 2-D, 3-C").
        # Students must not be able to read it through the API.
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if getattr(user, "role", None) == "student" and (data.get("body") or "").lstrip().lower().startswith("answer key"):
            data["body"] = ""
        return data


class StepSerializer(serializers.ModelSerializer):
    resource = ResourceSerializer(read_only=True)
    video_file = serializers.FileField(required=False, allow_null=True, write_only=True)
    video_url = serializers.SerializerMethodField()
    youtube_id = serializers.CharField(read_only=True)

    class Meta:
        model = Step
        fields = ["id", "lesson", "title", "step_type", "body", "link", "order", "resource",
                  "video_file", "video_url", "youtube_id"]

    def get_video_url(self, obj):
        """In-app streaming URL for an uploaded video (needs login), or None."""
        if not obj.video_file:
            return None
        from django.urls import reverse
        url = reverse("step_video", args=[obj.pk])
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url


class LessonSerializer(serializers.ModelSerializer):
    steps = StepSerializer(many=True, read_only=True)

    class Meta:
        model = Lesson
        fields = ["id", "module", "name", "description", "order", "steps"]


class ModuleSerializer(serializers.ModelSerializer):
    lessons = LessonSerializer(many=True, read_only=True)

    class Meta:
        model = Module
        fields = ["id", "course", "name", "description", "order", "lessons"]


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ["id", "name", "description", "number"]


# ---- Enrollment ----

class ClassSessionSerializer(serializers.ModelSerializer):
    join_link = serializers.ReadOnlyField(help_text="Saved Meet link, or an instant-meeting link if none is set.")

    class Meta:
        model = ClassSession
        fields = [
            "id", "course", "teacher", "name", "description", "start_date", "finish_date",
            "meeting_link", "join_link",
        ]


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ["id", "class_session", "student", "coach", "name", "invite"]
        read_only_fields = ["invite"]


class StepCompletionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StepCompletion
        fields = ["id", "student", "step", "completed_at", "answer", "status", "reviewed_by",
                  "reviewed_at", "review_note"]
        read_only_fields = ["id", "completed_at", "reviewed_by", "reviewed_at"]


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = ["id", "teacher", "student", "direction", "content", "created_at"]
        read_only_fields = ["id", "created_at"]


class MeetupSerializer(serializers.ModelSerializer):
    join_link = serializers.ReadOnlyField(help_text="Saved Meet link, or an instant-meeting link if none is set.")

    class Meta:
        model = Meetup
        fields = ["id", "student", "coach", "status", "scheduled_time", "notes", "meeting_link", "join_link"]


class ClassInviteSerializer(serializers.ModelSerializer):
    join_url = serializers.SerializerMethodField()
    is_usable = serializers.BooleanField(read_only=True)

    class Meta:
        model = ClassInvite
        fields = ["id", "class_session", "created_by", "coach", "token", "join_url", "created_at",
                  "expires_at", "max_uses", "uses", "is_active", "is_usable"]
        read_only_fields = ["id", "created_by", "token", "created_at", "uses"]

    def get_join_url(self, obj):
        from django.urls import reverse
        url = reverse("join_class", args=[obj.token])
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url


class JoinClassSerializer(serializers.Serializer):
    token = serializers.CharField(help_text="The invite token (the last part of the invite link).")


# ---- Communication ----

class AnnouncementSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(read_only=True)

    class Meta:
        model = Announcement
        fields = ["id", "title", "summary", "body", "category", "is_pinned", "author", "author_name", "created_at"]
        read_only_fields = ["id", "author", "created_at"]


class MessageSerializer(serializers.ModelSerializer):
    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = Message
        fields = ["id", "sender", "recipient", "subject", "body", "parent", "created_at", "read_at",
                  "is_read", "emailed"]
        read_only_fields = ["id", "sender", "created_at", "read_at", "emailed"]

    def validate_recipient(self, value):
        request = self.context.get("request")
        if request and value.pk == request.user.pk:
            raise serializers.ValidationError("You can't send a message to yourself.")
        return value


# ---- Auth ----

class SignupSerializer(serializers.Serializer):
    ROLE_CHOICES = [("student", "Student"), ("teacher", "Teacher"), ("coach", "Coach")]

    role = serializers.ChoiceField(choices=ROLE_CHOICES)
    username = serializers.CharField(max_length=150)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=True, help_text="A verification code is sent here.")
    password = serializers.CharField(write_only=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("That username is already taken.")
        return value

    def validate_password(self, value):
        password_validation.validate_password(value)
        return value


class SignupVerifySerializer(serializers.Serializer):
    pending_token = serializers.CharField()
    code = serializers.CharField(max_length=6, min_length=6)


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        password_validation.validate_password(value)
        return value
