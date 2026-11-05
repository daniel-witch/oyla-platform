import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


# A plain https://meet.google.com/new link starts a brand-new Google Meet
# call instantly the moment anyone opens it - no Google Calendar API,
# OAuth app, or API key needed. It's the fallback "Start Google Meet"
# button whenever a session/meetup doesn't have its own saved link.
GOOGLE_MEET_INSTANT_LINK = "https://meet.google.com/new"


class ClassSession(models.Model):
    """A teacher-led, time-boxed offering of a Course (tblCLASS)."""

    course = models.ForeignKey("catalog.Course", on_delete=models.CASCADE, related_name="class_sessions")
    teacher = models.ForeignKey("users.Teacher", on_delete=models.CASCADE, related_name="class_sessions")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start_date = models.DateTimeField()
    finish_date = models.DateTimeField(null=True, blank=True)
    meeting_link = models.URLField(
        blank=True,
        help_text="Paste a real Google Meet link (e.g. from a Google Calendar event) here. "
                   "Leave blank to let students/teacher start an instant Meet call instead.",
    )

    def __str__(self):
        return self.name

    @property
    def join_link(self) -> str:
        """The link to show on 'Join'/'Start' buttons - the saved link if set,
        otherwise a fresh Google Meet instant-meeting link."""
        return self.meeting_link or GOOGLE_MEET_INSTANT_LINK


class Group(models.Model):
    """Join entity linking one Student, one ClassSession, and one Coach (tblGROUP)."""

    class_session = models.ForeignKey(ClassSession, on_delete=models.CASCADE, related_name="groups")
    student = models.ForeignKey("users.Student", on_delete=models.CASCADE, related_name="class_groups")
    coach = models.ForeignKey("users.Coach", on_delete=models.CASCADE, related_name="class_groups",
                              null=True, blank=True)
    name = models.CharField(max_length=255, blank=True)
    invite = models.ForeignKey("ClassInvite", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="joined_groups",
                               help_text="The invite link the student used to join (if any).")

    class Meta:
        unique_together = ("class_session", "student")

    def __str__(self):
        return self.name or f"Group {self.pk}"


class StepCompletion(models.Model):
    """Tracks a student's progress on one Step.

    Video/text steps are self-marked by the student (status jumps straight
    to APPROVED). Quiz/practice steps are a real submission: the student's
    answer is saved with status=PENDING, and a teacher or coach who has that
    student (via a Group) reviews it and sets APPROVED/REJECTED.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Needs revision"

    student = models.ForeignKey("users.Student", on_delete=models.CASCADE, related_name="completed_steps")
    step = models.ForeignKey("catalog.Step", on_delete=models.CASCADE, related_name="completions")
    completed_at = models.DateTimeField(auto_now_add=True)
    answer = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.APPROVED)
    reviewed_by = models.ForeignKey(
        "users.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        help_text="The teacher or coach who approved/rejected this submission.",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        unique_together = ("student", "step")

    def __str__(self):
        return f"{self.student} — {self.step} ({self.status})"


class Feedback(models.Model):
    """Feedback between a teacher and a student - written by either side.

    direction says who wrote it: the teacher (about the student) or the
    student (about the teacher / the class)."""

    class Direction(models.TextChoices):
        TEACHER_TO_STUDENT = "teacher_to_student", "Teacher → Student"
        STUDENT_TO_TEACHER = "student_to_teacher", "Student → Teacher"

    teacher = models.ForeignKey("users.Teacher", on_delete=models.CASCADE, related_name="feedbacks_given")
    student = models.ForeignKey("users.Student", on_delete=models.CASCADE, related_name="feedbacks_received")
    direction = models.CharField(max_length=20, choices=Direction.choices,
                                 default=Direction.TEACHER_TO_STUDENT)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def author(self):
        return self.teacher if self.direction == self.Direction.TEACHER_TO_STUDENT else self.student

    @property
    def recipient(self):
        return self.student if self.direction == self.Direction.TEACHER_TO_STUDENT else self.teacher


class Meetup(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        SCHEDULED = "scheduled", "Scheduled"
        RESOLVED = "resolved", "Resolved"

    student = models.ForeignKey("users.Student", on_delete=models.CASCADE, related_name="meetups")
    coach = models.ForeignKey("users.Coach", on_delete=models.CASCADE, related_name="meetups", null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    scheduled_time = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    meeting_link = models.URLField(
        blank=True,
        help_text="Paste a real Google Meet link here once you schedule this meetup. "
                   "Leave blank to let both sides start an instant Meet call instead.",
    )

    def __str__(self):
        return f"Meetup: {self.student} × {self.coach or 'unassigned'} ({self.status})"

    @property
    def join_link(self) -> str:
        return self.meeting_link or GOOGLE_MEET_INSTANT_LINK


def _new_invite_token():
    return secrets.token_urlsafe(12)


class ClassInvite(models.Model):
    """An invite link a teacher or coach creates for one class session.

    Students can only join a class through one of these links (/join/<token>/).
    """

    class_session = models.ForeignKey(ClassSession, on_delete=models.CASCADE, related_name="invites")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name="class_invites")
    coach = models.ForeignKey("users.Coach", null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="+",
                              help_text="Coach the joining students are assigned to "
                                        "(automatically the inviter when a coach creates the link).")
    token = models.CharField(max_length=32, unique=True, default=_new_invite_token, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    max_uses = models.PositiveIntegerField(null=True, blank=True, help_text="Empty = unlimited")
    uses = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invite to {self.class_session} ({self.token})"

    def problem(self):
        """Why this link can't be used right now, or '' if it can."""
        if not self.is_active:
            return "This invite link has been turned off."
        if self.expires_at and timezone.now() > self.expires_at:
            return "This invite link has expired."
        if self.max_uses is not None and self.uses >= self.max_uses:
            return "This invite link has already been used the maximum number of times."
        return ""

    @property
    def is_usable(self):
        return not self.problem()

    def join(self, student):
        """Adds the student to the class. Returns (group, created). Raises ValueError with a
        readable message if the link can't be used."""
        msg = self.problem()
        if msg:
            raise ValueError(msg)
        existing = Group.objects.filter(class_session=self.class_session, student=student).first()
        if existing:
            return existing, False
        coach = self.coach
        if coach is None and getattr(self.created_by, "role", None) == "coach":
            coach = self.created_by.coach
        group = Group.objects.create(
            class_session=self.class_session, student=student, coach=coach,
            name=self.class_session.name, invite=self,
        )
        if not student.enrolled_course_id:
            student.enrolled_course = self.class_session.course
            student.save()
        ClassInvite.objects.filter(pk=self.pk).update(uses=models.F("uses") + 1)
        self.refresh_from_db(fields=["uses"])
        return group, True
