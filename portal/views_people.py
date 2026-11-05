"""Profile (#1, #6), feedback in both directions (#11) and invite links (#5)."""
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from enrollment.models import ClassInvite, ClassSession, Feedback, Group
from users.models import Coach, Student, Teacher, User


# ------------------------------------------------------------------ profile

class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["photo", "first_name", "last_name", "email", "phone_number", "birth_date",
                  "gender", "perm_address"]
        widgets = {"birth_date": forms.DateInput(attrs={"type": "date"})}
        labels = {"perm_address": "Address", "phone_number": "Phone"}

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and hasattr(photo, "size") and photo.size > 3 * 1024 * 1024:
            raise forms.ValidationError("Please choose a photo smaller than 3 MB.")
        return photo


@login_required
def profile(request):
    user = request.user
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=user)
        if request.POST.get("remove_photo"):
            user.photo.delete(save=True)
            messages.info(request, "Photo removed.")
            return redirect("profile")
        if form.is_valid():
            form.save()
            messages.info(request, "Profile saved.")
            return redirect("profile")
    else:
        form = ProfileForm(instance=user)
    return render(request, "portal/profile.html", {"form": form})


# ------------------------------------------------------------------ feedback

def _teachers_of(student):
    return Teacher.objects.filter(class_sessions__groups__student=student).distinct()


def _students_of(teacher):
    return Student.objects.filter(class_groups__class_session__teacher=teacher).distinct()


@login_required
def feedback(request):
    """Students write feedback to their teachers; teachers write feedback to
    their students. Both see what they sent and what they received."""
    role = getattr(request.user, "role", None)
    if role not in ("student", "teacher"):
        messages.error(request, "Feedback is for students and teachers.")
        return redirect("dashboard")

    if role == "student":
        me = request.user.student
        people = _teachers_of(me)
        received = Feedback.objects.filter(student=me, direction=Feedback.Direction.TEACHER_TO_STUDENT)
        sent = Feedback.objects.filter(student=me, direction=Feedback.Direction.STUDENT_TO_TEACHER)
    else:
        me = request.user.teacher
        people = _students_of(me)
        received = Feedback.objects.filter(teacher=me, direction=Feedback.Direction.STUDENT_TO_TEACHER)
        sent = Feedback.objects.filter(teacher=me, direction=Feedback.Direction.TEACHER_TO_STUDENT)

    if request.method == "POST":
        content = request.POST.get("content", "").strip()
        other = people.filter(pk=request.POST.get("to")).first()
        if not other:
            messages.error(request, "Choose who the feedback is for.")
        elif not content:
            messages.error(request, "Feedback can't be empty.")
        else:
            if role == "student":
                Feedback.objects.create(student=me, teacher=other, content=content,
                                        direction=Feedback.Direction.STUDENT_TO_TEACHER)
            else:
                Feedback.objects.create(teacher=me, student=other, content=content,
                                        direction=Feedback.Direction.TEACHER_TO_STUDENT)
            messages.info(request, f"Feedback sent to {other.display_name}.")
            return redirect("feedback")

    return render(request, "portal/feedback.html", {
        "people": people, "received": received.select_related("teacher", "student"),
        "sent": sent.select_related("teacher", "student"), "is_student": role == "student",
        "preselect": request.GET.get("to", ""),
    })


# ------------------------------------------------------------------ invites

def _sessions_for_inviter(user):
    role = getattr(user, "role", None)
    if role == "teacher":
        return ClassSession.objects.filter(teacher=user.teacher)
    if role == "coach" or user.is_superuser:
        return ClassSession.objects.all()
    return ClassSession.objects.none()


@login_required
def invites(request):
    """Teachers and coaches create invite links; only these let students join a class."""
    user = request.user
    role = getattr(user, "role", None)
    if role not in ("teacher", "coach") and not user.is_superuser:
        messages.error(request, "Only teachers and coaches can create invite links.")
        return redirect("dashboard")

    sessions = _sessions_for_inviter(user).select_related("course").order_by("start_date")
    my_invites = ClassInvite.objects.filter(created_by=user).select_related("class_session__course", "coach")

    if request.method == "POST":
        action = request.POST.get("action", "create")
        if action == "deactivate":
            inv = get_object_or_404(ClassInvite, pk=request.POST.get("invite_id"), created_by=user)
            inv.is_active = False
            inv.save(update_fields=["is_active"])
            messages.info(request, "Invite link turned off.")
            return redirect("invites")

        session = sessions.filter(pk=request.POST.get("class_session")).first()
        if not session:
            messages.error(request, "Choose one of your class sessions.")
            return redirect("invites")
        coach = None
        if role == "coach":
            coach = user.coach
        elif request.POST.get("coach"):
            coach = Coach.objects.filter(pk=request.POST["coach"]).first()
        days = request.POST.get("days", "7")
        max_uses = request.POST.get("max_uses", "").strip()
        inv = ClassInvite.objects.create(
            class_session=session, created_by=user, coach=coach,
            expires_at=timezone.now() + timedelta(days=int(days)) if days.isdigit() and int(days) > 0 else None,
            max_uses=int(max_uses) if max_uses.isdigit() and int(max_uses) > 0 else None,
        )
        messages.info(request, "Invite link created — copy it and send it to your students.")
        return redirect(f"{reverse('invites')}#invite-{inv.pk}")

    for inv in my_invites:
        inv.url = request.build_absolute_uri(reverse("join_class", args=[inv.token]))
    return render(request, "portal/invites.html", {
        "sessions": sessions, "invites": my_invites, "coaches": Coach.objects.order_by("first_name", "username"),
        "is_coach": role == "coach",
    })


def join_class(request, token):
    """/join/<token>/ - the ONLY way a student joins a class."""
    invite = ClassInvite.objects.filter(token=token).select_related("class_session__course", "created_by").first()
    if not request.user.is_authenticated:
        if invite:
            request.session["pending_invite"] = token
        messages.info(request, "Log in or sign up as a student to join the class.")
        return redirect(f"{reverse('login')}?next={reverse('join_class', args=[token])}")

    if getattr(request.user, "role", None) != "student":
        messages.error(request, "Only students can join a class with an invite link.")
        return redirect("dashboard")
    if not invite:
        messages.error(request, "That invite link doesn't exist. Ask your teacher or coach for a new one.")
        return redirect("enrollments")

    try:
        group, created = invite.join(request.user.student)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect("enrollments")
    course = invite.class_session.course
    if created:
        messages.info(request, f"You joined “{invite.class_session.name}”. {course.name} is now in My Enrollments.")
    else:
        messages.info(request, f"You're already in “{invite.class_session.name}”.")
    return redirect("course_detail", course_id=course.pk)


@login_required
def join_by_code(request):
    """The 'Join a class' box on My Enrollments: paste the link or just its code."""
    raw = request.POST.get("code", "").strip().rstrip("/")
    token = raw.split("/join/")[-1].split("/")[0] if "/join/" in raw else raw
    if not token or "/" in token or len(token) > 64:
        messages.error(request, "Paste the invite link you received.")
        return redirect("enrollments")
    return redirect("join_class", token=token)
