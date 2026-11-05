"""Builds the left-hand menu for every page, based on the user's role."""
from django.urls import reverse

# (label, url name, url names that light this item up)
STUDENT_MENU = [
    ("My Enrollments", "enrollments", {"enrollments", "course_detail", "module_detail", "step_detail", "dashboard"}),
    ("Study Module", "study_module", {"study_module", "study_module_course"}),
    ("Announcements", "announcements", {"announcements", "announcement_detail"}),
    ("Mail", "mail_inbox", {"mail_inbox", "mail_sent", "mail_compose", "mail_detail"}),
    ("Feedback", "feedback", {"feedback"}),
]
STAFF_MENU = [
    ("Dashboard", "dashboard", {"dashboard", "step_detail"}),
    ("Study Module", "study_module", {"study_module", "study_module_course"}),
    ("Announcements", "announcements", {"announcements", "announcement_detail", "announcement_new"}),
    ("Mail", "mail_inbox", {"mail_inbox", "mail_sent", "mail_compose", "mail_detail"}),
    ("Invite links", "invites", {"invites"}),
]
TEACHER_EXTRA = [("Feedback", "feedback", {"feedback"})]


def nav(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    role = getattr(user, "role", "") or ""
    if role == "student":
        items = STUDENT_MENU
    elif role == "teacher":
        items = STAFF_MENU + TEACHER_EXTRA
    elif role == "coach":
        items = STAFF_MENU
    else:  # admin accounts without a role
        items = STAFF_MENU

    current = request.resolver_match.url_name if request.resolver_match else ""
    menu = [{"label": label, "url": reverse(name), "active": current in names, "key": name}
            for label, name, names in items]

    from communication.models import Message
    unread = Message.objects.filter(recipient=user, read_at__isnull=True).count()
    return {"menu": menu, "unread_mail": unread}
