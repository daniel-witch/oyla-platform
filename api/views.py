from django.contrib.auth import authenticate
from django.core import signing
from django.db.models import Q
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import User, Student, Teacher, Coach, EmailVerificationCode
from users.verification import (
    make_pending_signup_token, read_pending_signup_token,
    send_verification_email, create_role_user_from_payload,
)
from catalog.models import Course, Module, Lesson, Step, Resource
from enrollment.models import ClassSession, ClassInvite, Group, StepCompletion, Feedback, Meetup
from communication.models import Announcement, Message
from portal.access import annotate_modules, course_progress

from .permissions import RoleWritePermission, access_level
from .serializers import (
    UserSerializer, UserAdminSerializer, StudentSerializer, TeacherSerializer, CoachSerializer,
    CourseSerializer, ModuleSerializer, LessonSerializer, StepSerializer, ResourceSerializer,
    ClassSessionSerializer, GroupSerializer, StepCompletionSerializer, FeedbackSerializer, MeetupSerializer,
    SignupSerializer, SignupVerifySerializer, PasswordChangeSerializer,
    ClassInviteSerializer, JoinClassSerializer, AnnouncementSerializer, MessageSerializer,
)


def _role(user):
    return getattr(user, "role", None)


def _is_admin(user):
    return user.is_superuser or user.is_staff


# ---- Users ----

class UserViewSet(viewsets.ModelViewSet):
    """All user accounts (students, teachers, coaches and administrators).
    Members can read; only administrators can create, change or delete accounts.
    Creating here makes a plain account; send "is_staff": true to make an administrator."""
    permission_classes = [RoleWritePermission]
    write_roles = ()
    queryset = User.objects.all().order_by("id")
    serializer_class = UserAdminSerializer
    filterset_fields = {"role": "role", "is_staff": "is_staff", "is_active": "is_active"}
    search_fields = ["username", "first_name", "last_name", "email"]
    ordering_fields = ["id", "username", "date_joined", "last_name"]

    def perform_destroy(self, instance):
        if instance.pk == self.request.user.pk:
            raise PermissionDenied("You can't delete your own account while logged in with it.")
        instance.delete()


class StudentViewSet(viewsets.ModelViewSet):
    permission_classes = [RoleWritePermission]
    write_roles = ()
    queryset = Student.objects.all().order_by("id")
    serializer_class = StudentSerializer
    filterset_fields = {"enrolled_course": "enrolled_course", "gender": "gender"}
    search_fields = ["username", "first_name", "last_name", "email"]
    ordering_fields = ["id", "username", "last_name", "date_joined"]


class TeacherViewSet(viewsets.ModelViewSet):
    permission_classes = [RoleWritePermission]
    write_roles = ()
    queryset = Teacher.objects.all().order_by("id")
    serializer_class = TeacherSerializer
    filterset_fields = {"gender": "gender"}
    search_fields = ["username", "first_name", "last_name", "email"]
    ordering_fields = ["id", "username", "last_name", "date_joined"]


class CoachViewSet(viewsets.ModelViewSet):
    permission_classes = [RoleWritePermission]
    write_roles = ()
    queryset = Coach.objects.all().order_by("id")
    serializer_class = CoachSerializer
    filterset_fields = {"gender": "gender"}
    search_fields = ["username", "first_name", "last_name", "email"]
    ordering_fields = ["id", "username", "last_name", "date_joined"]


# ---- Catalog ----

class CourseViewSet(viewsets.ModelViewSet):
    permission_classes = [RoleWritePermission]
    write_roles = ("teacher", "coach")
    guest_read = True  # guests may browse the course catalog
    queryset = Course.objects.all().order_by("id")
    serializer_class = CourseSerializer
    filterset_fields = {"number": "number"}
    search_fields = ["name", "description", "number"]
    ordering_fields = ["id", "name", "number"]


class ModuleViewSet(viewsets.ModelViewSet):
    permission_classes = [RoleWritePermission]
    write_roles = ("teacher", "coach")
    guest_read = True
    queryset = Module.objects.all().order_by("course_id", "order", "id")
    serializer_class = ModuleSerializer
    filterset_fields = {"course": "course"}
    search_fields = ["name", "description"]
    ordering_fields = ["id", "order", "name"]


class LessonViewSet(viewsets.ModelViewSet):
    permission_classes = [RoleWritePermission]
    write_roles = ("teacher", "coach")
    guest_read = True
    queryset = Lesson.objects.all().order_by("module_id", "order", "id")
    serializer_class = LessonSerializer
    filterset_fields = {"module": "module", "course": "module__course"}
    search_fields = ["name", "description"]
    ordering_fields = ["id", "order", "name"]


class StepViewSet(viewsets.ModelViewSet):
    permission_classes = [RoleWritePermission]
    write_roles = ("teacher", "coach")
    queryset = Step.objects.all().order_by("lesson_id", "order", "id")
    serializer_class = StepSerializer
    filterset_fields = {"lesson": "lesson", "module": "lesson__module", "course": "lesson__module__course",
                        "step_type": "step_type"}
    search_fields = ["title", "body"]
    ordering_fields = ["id", "order", "title"]


class ResourceViewSet(viewsets.ModelViewSet):
    permission_classes = [RoleWritePermission]
    write_roles = ("teacher", "coach")
    queryset = Resource.objects.all().order_by("id")
    serializer_class = ResourceSerializer
    filterset_fields = {"step": "step", "resource_type": "resource_type"}
    search_fields = ["body", "link"]
    ordering_fields = ["id"]


# ---- Enrollment ----

class ClassSessionViewSet(viewsets.ModelViewSet):
    permission_classes = [RoleWritePermission]
    write_roles = ("teacher",)
    queryset = ClassSession.objects.all().order_by("start_date", "id")
    serializer_class = ClassSessionSerializer
    filterset_fields = {"course": "course", "teacher": "teacher"}
    search_fields = ["name", "description"]
    ordering_fields = ["id", "start_date", "name"]


class GroupViewSet(viewsets.ModelViewSet):
    """Students can't add themselves to a class here - they join only through an
    invite link (POST /api/invites/join/)."""
    permission_classes = [RoleWritePermission]
    write_roles = ("teacher", "coach")
    queryset = Group.objects.all().order_by("id")
    serializer_class = GroupSerializer
    filterset_fields = {"class_session": "class_session", "student": "student", "coach": "coach",
                        "course": "class_session__course"}
    search_fields = ["name"]
    ordering_fields = ["id", "name"]

    def create(self, request, *args, **kwargs):
        if _role(request.user) == "student":
            raise PermissionDenied("Students join a class only through an invite link: POST /api/invites/join/.")
        return super().create(request, *args, **kwargs)


class StepCompletionViewSet(viewsets.ModelViewSet):
    """A completed step can't be undone: students can create a completion but
    can't change or delete it. Only admins can delete completions."""
    permission_classes = [RoleWritePermission]
    write_roles = ("student", "teacher", "coach")
    queryset = StepCompletion.objects.all().order_by("-completed_at", "id")
    serializer_class = StepCompletionSerializer
    filterset_fields = {"student": "student", "step": "step", "status": "status",
                        "lesson": "step__lesson", "course": "step__lesson__module__course"}
    search_fields = ["answer", "review_note"]
    ordering_fields = ["id", "completed_at", "status"]

    def perform_update(self, serializer):
        if _role(self.request.user) == "student":
            raise PermissionDenied("A completed step can't be changed or undone.")
        serializer.save()

    def perform_destroy(self, instance):
        if not _is_admin(self.request.user):
            raise PermissionDenied("A completed step can't be undone. Only an admin can delete it.")
        instance.delete()


class FeedbackViewSet(viewsets.ModelViewSet):
    """Feedback in both directions: teacher_to_student and student_to_teacher."""
    permission_classes = [RoleWritePermission]
    write_roles = ("student", "teacher")
    queryset = Feedback.objects.all().order_by("-created_at", "id")
    serializer_class = FeedbackSerializer
    filterset_fields = {"student": "student", "teacher": "teacher", "direction": "direction"}
    search_fields = ["content"]
    ordering_fields = ["id", "created_at"]

    def create(self, request, *args, **kwargs):
        # The author is always the logged-in student/teacher, so they don't have to send their own id.
        role = _role(request.user)
        if not hasattr(request.data, "copy") or isinstance(request.data, (list, str)):
            return Response({"detail": "Send a JSON object, e.g. {\"content\": \"...\"}."},
                            status=status.HTTP_400_BAD_REQUEST)
        if role in ("student", "teacher"):
            data = request.data.copy()
            data[role] = request.user.pk
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        role = _role(self.request.user)
        if role == "student":
            serializer.save(student=self.request.user.student, direction=Feedback.Direction.STUDENT_TO_TEACHER)
        elif role == "teacher":
            serializer.save(teacher=self.request.user.teacher, direction=Feedback.Direction.TEACHER_TO_STUDENT)
        else:
            serializer.save()


class ClassInviteViewSet(viewsets.ModelViewSet):
    """Invite links. Teachers, coaches and admins create them; students use them
    with POST /api/invites/join/."""
    serializer_class = ClassInviteSerializer
    filterset_fields = {"class_session": "class_session", "coach": "coach", "is_active": "is_active"}
    ordering_fields = ["id", "created_at", "expires_at"]

    def get_queryset(self):
        user = self.request.user
        if _is_admin(user):
            return ClassInvite.objects.all().order_by("-created_at")
        return ClassInvite.objects.filter(created_by=user).order_by("-created_at")

    def perform_create(self, serializer):
        user = self.request.user
        role = _role(user)
        if role not in ("teacher", "coach") and not _is_admin(user):
            raise PermissionDenied("Only teachers, coaches and admins can create invite links.")
        session = serializer.validated_data["class_session"]
        if role == "teacher" and session.teacher_id != user.pk:
            raise PermissionDenied("You can only invite students to your own class sessions.")
        extra = {"created_by": user}
        if role == "coach":
            extra["coach"] = user.coach
        serializer.save(**extra)


class JoinClassView(APIView):
    """POST {"token": "..."} (student) -> joins the class behind that invite link."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if _role(request.user) != "student":
            return Response({"detail": "Only students can join a class."}, status=status.HTTP_403_FORBIDDEN)
        serializer = JoinClassSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invite = ClassInvite.objects.filter(token=serializer.validated_data["token"]).first()
        if not invite:
            return Response({"detail": "Invite link not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            group, created = invite.join(request.user.student)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Joined." if created else "Already in this class.",
                         "group": GroupSerializer(group).data},
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class MyEnrollmentsView(APIView):
    """GET (student) -> My Enrollments: courses, their modules and which ones are open."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if _role(request.user) != "student":
            return Response({"detail": "Only students have enrollments."}, status=status.HTTP_403_FORBIDDEN)
        student = request.user.student
        data = []
        for course in Course.objects.filter(pk__in=student.course_ids()).order_by("name"):
            data.append({
                "id": course.pk, "name": course.name, "number": course.number,
                "progress": course_progress(student, course),
                "modules": [{
                    "id": m.pk, "name": m.name, "order": m.order, "state": m.state,
                    "finished_steps": m.finished_steps, "total_steps": m.total_steps,
                    "lessons": [{"id": l.pk, "name": l.name,
                                 "steps": [{"id": s.pk, "name": s.display_name, "step_type": s.step_type}
                                           for s in l.steps.all()] if m.is_open else []}
                                for l in m.lessons.all()],
                } for m in annotate_modules(student, course)],
            })
        return Response({"student_id": student.code, "courses": data})


class DashboardView(APIView):
    """GET /api/dashboard/ -> one answer combined from several entities.

    Everyone logged in gets: their profile (User), access level, unread messages
    (Message), the latest announcements (Announcement) and their upcoming class
    sessions (ClassSession + Course + Teacher). Then, by role:
      student -> courses with progress (Course + Step + StepCompletion), groups and coaches
                 (Group + Coach), submissions waiting for review, feedback received
      teacher -> class sessions with student counts, submissions to review, feedback received
      coach   -> groups with their students, open meetup requests
      admin   -> how many records each entity has
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        role = _role(user)
        level = access_level(user)
        now = timezone.now()

        def session_data(qs):
            return [{"id": cs.pk, "name": cs.name, "course": cs.course.name, "course_id": cs.course_id,
                     "teacher": cs.teacher.get_full_name() or cs.teacher.username,
                     "start_date": cs.start_date, "join_link": cs.join_link}
                    for cs in qs.select_related("course", "teacher").order_by("start_date")[:5]]

        data = {
            "profile": UserSerializer(user, context={"request": request}).data,
            "access_level": level,
            "role": role or ("administrator" if level == "administrator" else ""),
            "unread_messages": Message.objects.filter(recipient=user, read_at__isnull=True).count(),
            "latest_announcements": [
                {"id": a.pk, "title": a.title, "category": a.category, "is_pinned": a.is_pinned,
                 "created_at": a.created_at}
                for a in Announcement.objects.order_by("-is_pinned", "-created_at")[:3]],
        }

        if role == "student":
            st = user.student
            groups = Group.objects.filter(student=st).select_related("class_session__course", "coach")
            data["courses"] = [{"id": c.pk, "name": c.name, "number": c.number,
                                "progress": course_progress(st, c)}
                               for c in Course.objects.filter(pk__in=st.course_ids()).order_by("name")]
            data["groups"] = [{"id": g.pk, "name": g.name, "class_session": g.class_session.name,
                               "course": g.class_session.course.name,
                               "coach": (g.coach.get_full_name() or g.coach.username) if g.coach else None}
                              for g in groups]
            data["upcoming_sessions"] = session_data(
                ClassSession.objects.filter(groups__student=st, start_date__gte=now).distinct())
            data["submissions_pending_review"] = StepCompletion.objects.filter(
                student=st, status=StepCompletion.Status.PENDING).count()
            data["feedback_received"] = Feedback.objects.filter(
                student=st, direction=Feedback.Direction.TEACHER_TO_STUDENT).count()
        elif role == "teacher":
            t = user.teacher
            sessions = ClassSession.objects.filter(teacher=t).select_related("course")
            data["class_sessions"] = [{"id": cs.pk, "name": cs.name, "course": cs.course.name,
                                       "students": cs.groups.count(), "start_date": cs.start_date}
                                      for cs in sessions.order_by("start_date")]
            data["upcoming_sessions"] = session_data(sessions.filter(start_date__gte=now))
            data["submissions_to_review"] = StepCompletion.objects.filter(
                status=StepCompletion.Status.PENDING,
                student__class_groups__class_session__teacher=t).distinct().count()
            data["feedback_received"] = Feedback.objects.filter(
                teacher=t, direction=Feedback.Direction.STUDENT_TO_TEACHER).count()
        elif role == "coach":
            c = user.coach
            groups = Group.objects.filter(coach=c).select_related("student", "class_session__course")
            data["groups"] = [{"id": g.pk, "name": g.name, "class_session": g.class_session.name,
                               "course": g.class_session.course.name,
                               "student": g.student.get_full_name() or g.student.username,
                               "student_id": g.student.student_code}
                              for g in groups]
            data["upcoming_sessions"] = session_data(
                ClassSession.objects.filter(groups__coach=c, start_date__gte=now).distinct())
            data["open_meetups"] = Meetup.objects.filter(
                student__class_groups__coach=c).exclude(status="resolved").distinct().count()
        if level == "administrator":
            data["totals"] = {
                "users": User.objects.count(), "students": Student.objects.count(),
                "teachers": Teacher.objects.count(), "coaches": Coach.objects.count(),
                "courses": Course.objects.count(), "modules": Module.objects.count(),
                "lessons": Lesson.objects.count(), "steps": Step.objects.count(),
                "class_sessions": ClassSession.objects.count(), "groups": Group.objects.count(),
                "submissions_pending": StepCompletion.objects.filter(status=StepCompletion.Status.PENDING).count(),
            }
            data.setdefault("upcoming_sessions", session_data(ClassSession.objects.filter(start_date__gte=now)))
        return Response(data)


# ---- Communication ----

class AnnouncementViewSet(viewsets.ModelViewSet):
    """Announcements board. Everyone reads (guests too); teachers, coaches and admins publish."""
    permission_classes = [RoleWritePermission]
    write_roles = ("teacher", "coach")
    guest_read = True
    queryset = Announcement.objects.select_related("author").order_by("-is_pinned", "-created_at")
    serializer_class = AnnouncementSerializer
    filterset_fields = {"category": "category", "is_pinned": "is_pinned", "author": "author"}
    search_fields = ["title", "summary", "body"]
    ordering_fields = ["id", "created_at", "title"]

    def _check_can_write(self):
        if _role(self.request.user) not in ("teacher", "coach") and not _is_admin(self.request.user):
            raise PermissionDenied("Only teachers, coaches and admins can publish announcements.")

    def perform_create(self, serializer):
        self._check_can_write()
        serializer.save(author=self.request.user)

    def perform_update(self, serializer):
        self._check_can_write()
        if serializer.instance.author_id not in (None, self.request.user.pk) and not _is_admin(self.request.user):
            raise PermissionDenied("You can only edit your own announcements.")
        serializer.save()

    def perform_destroy(self, instance):
        self._check_can_write()
        if instance.author_id != self.request.user.pk and not _is_admin(self.request.user):
            raise PermissionDenied("You can only delete your own announcements.")
        instance.delete()


class MessageViewSet(viewsets.ModelViewSet):
    """Integrated mail. You only see messages you sent or received.
    ?box=inbox or ?box=sent filters. Opening a received message marks it read.
    Sending also emails a copy to the recipient. The sender can edit the subject
    and text (PUT/PATCH) until the recipient has read it."""
    serializer_class = MessageSerializer
    filterset_fields = {"recipient": "recipient", "sender": "sender", "unread": "read_at__isnull"}
    search_fields = ["subject", "body"]
    ordering_fields = ["id", "created_at"]

    def get_queryset(self):
        user = self.request.user
        qs = Message.objects.filter(Q(sender=user) | Q(recipient=user))
        box = self.request.query_params.get("box")
        if box == "inbox":
            qs = qs.filter(recipient=user)
        elif box == "sent":
            qs = qs.filter(sender=user)
        return qs.order_by("-created_at")

    def perform_update(self, serializer):
        msg = serializer.instance
        if msg.sender_id != self.request.user.pk:
            raise PermissionDenied("Only the sender can edit a message.")
        if msg.read_at:
            raise PermissionDenied("This message was already read, so it can't be edited any more.")
        serializer.save(recipient=msg.recipient, parent=msg.parent)

    def retrieve(self, request, *args, **kwargs):
        msg = self.get_object()
        if msg.recipient_id == request.user.pk:
            msg.mark_read()
        return Response(self.get_serializer(msg).data)

    def perform_create(self, serializer):
        msg = serializer.save(sender=self.request.user)
        msg.send_email_copy()


class MeetupViewSet(viewsets.ModelViewSet):
    permission_classes = [RoleWritePermission]
    write_roles = ("student", "coach")
    queryset = Meetup.objects.all().order_by("-id")
    serializer_class = MeetupSerializer
    filterset_fields = {"student": "student", "coach": "coach", "status": "status"}
    search_fields = ["notes"]
    ordering_fields = ["id", "scheduled_time", "status"]


# ---- Auth ----
#
# Signup is two steps, matching the website's flow exactly (same shared
# users.verification helpers under the hood):
#   1. POST /api/auth/signup/         -> validates + sends a code, returns a pending_token
#   2. POST /api/auth/signup/verify/  -> pending_token + code -> creates the account, returns an auth token

class SignupView(APIView):
    throttle_scope = "login"
    """Step 1: validate signup data, email a 6-digit code, return a pending_token.
    No account is created yet."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        pending_token = make_pending_signup_token(data)
        code_obj = EmailVerificationCode.issue(data["email"])
        send_verification_email(data["email"], code_obj.code)

        return Response(
            {
                "detail": "Verification code sent. POST it with pending_token to /api/auth/signup/verify/.",
                "pending_token": pending_token,
            },
            status=status.HTTP_201_CREATED,
        )


class SignupVerifyView(APIView):
    throttle_scope = "login"
    """Step 2: pending_token + code -> creates the Student/Teacher/Coach, returns an auth token."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = SignupVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            payload = read_pending_signup_token(data["pending_token"])
        except signing.SignatureExpired:
            return Response({"detail": "Pending signup expired. Request a new code."},
                             status=status.HTTP_400_BAD_REQUEST)
        except signing.BadSignature:
            return Response({"detail": "Invalid pending_token."}, status=status.HTTP_400_BAD_REQUEST)

        if not EmailVerificationCode.verify_and_consume(payload["email"], data["code"]):
            return Response({"detail": "Invalid or expired code."}, status=status.HTTP_400_BAD_REQUEST)

        user = create_role_user_from_payload(payload)
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {"token": token.key, "user": UserSerializer(user).data},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """POST username/password -> returns an auth token for use as 'Authorization: Token <key>'."""
    permission_classes = [permissions.AllowAny]
    throttle_scope = "login"

    def post(self, request):
        if not isinstance(request.data, dict) and not hasattr(request.data, "getlist"):
            return Response({"detail": "Send a JSON object with username and password."},
                            status=status.HTTP_400_BAD_REQUEST)
        username = request.data.get("username")
        password = request.data.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            return Response({"detail": "username and password must be text."}, status=status.HTTP_400_BAD_REQUEST)
        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": UserSerializer(user).data})


class LogoutView(APIView):
    """POST (authenticated) -> deletes the caller's token."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordChangeView(APIView):
    throttle_scope = "login"
    """POST old_password/new_password (authenticated) -> changes password, rotates token."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["old_password"]):
            return Response({"detail": "Current password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        Token.objects.filter(user=user).delete()
        token = Token.objects.create(user=user)
        return Response({"detail": "Password changed.", "token": token.key})


class MeView(APIView):
    """GET -> the caller's profile (with personal ID and photo).
    PATCH -> update your own profile; send multipart/form-data to upload a photo."""
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        return Response(UserSerializer(request.user, context={"request": request}).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
