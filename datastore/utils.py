"""Shared helpers for the JSON data feature (used by both the API and the website)."""
import json

from django.db.models import Q
from django.utils.translation import gettext as _

from enrollment.models import Group
from .models import JsonRecord

MAX_RECORD_BYTES = 1_000_000      # 1 MB per record
MAX_RECORDS_PER_STUDENT = 200

STAFF_ROLES = ("teacher", "coach")


def role_of(user):
    return getattr(user, "role", "") or ""


def is_teacher_or_coach(user):
    return bool(user and user.is_authenticated and (user.is_superuser or role_of(user) in STAFF_ROLES))


def visible_records(user):
    """Records a user is allowed to SEE.

    - superuser: everything
    - teacher: own records + records of students in their class sessions
    - coach:   own records + records of students in their groups
    - student (and anyone else): only their own records
    """
    qs = JsonRecord.objects.select_related("created_by")
    if user.is_superuser:
        return qs
    role = role_of(user)
    if role == "teacher":
        student_ids = Group.objects.filter(class_session__teacher_id=user.pk).values("student_id")
        return qs.filter(Q(created_by=user) | Q(created_by_id__in=student_ids))
    if role == "coach":
        student_ids = Group.objects.filter(coach_id=user.pk).values("student_id")
        return qs.filter(Q(created_by=user) | Q(created_by_id__in=student_ids))
    return qs.filter(created_by=user)


def filter_records(qs, search="", category=""):
    if category:
        qs = qs.filter(category__iexact=category)
    if search:
        qs = qs.filter(
            Q(title__icontains=search) | Q(category__icontains=search)
            | Q(created_by__username__icontains=search)
            | Q(created_by__first_name__icontains=search)
            | Q(created_by__last_name__icontains=search)
        )
    return qs


def json_size(data):
    return len(json.dumps(data, ensure_ascii=False).encode("utf-8"))


def check_data_rules(data):
    """Return an error message string, or None if the data is acceptable."""
    if not isinstance(data, (dict, list)):
        return _('Your JSON must start with { (an object) or [ (a list). '
                 'Example: {"name": "Aruzhan", "grade": 10}')
    if json_size(data) > MAX_RECORD_BYTES:
        return _("This JSON is too big. The limit is 1 MB per record - try splitting it into smaller parts.")
    return None


def over_record_limit(user):
    """Students may keep at most MAX_RECORDS_PER_STUDENT records."""
    if role_of(user) != "student" or user.is_superuser:
        return False
    return JsonRecord.objects.filter(created_by=user).count() >= MAX_RECORDS_PER_STUDENT


def limit_message():
    return _("You already have %(n)s saved items, which is the maximum. "
             "Delete some old ones before adding new ones.") % {"n": MAX_RECORDS_PER_STUDENT}


# ---- Friendly JSON error messages (for high school students) ----

_FRIENDLY = [
    ("Expecting ',' delimiter", "You're missing a comma (,) here - put one between the items."),
    ("Expecting ':' delimiter", 'You\'re missing a colon (:) between a name and its value, like "age": 15.'),
    ("Expecting property name enclosed in double quotes",
     'Names must be in double quotes, like "name". Also check for an extra comma right before } .'),
    ("Expecting value", "A value is missing here (or there's an extra comma, or text without quotes)."),
    ("Unterminated string", 'A piece of text is missing its closing double quote (").'),
    ("Invalid control character", "Text inside quotes can't go onto a new line. Keep it on one line."),
    ("Extra data", "There is extra text after the end of your JSON. Remove it, or wrap everything in [ ]."),
    ("Invalid \\escape", "There's a backslash (\\) that isn't allowed. Use \\\\ for a real backslash."),
]


class FriendlyJSONError(ValueError):
    def __init__(self, message, line=None, column=None, line_text=""):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column
        self.line_text = line_text


def parse_json_text(text):
    """json.loads with a student-friendly error message (with line + column)."""
    if text is None or not str(text).strip():
        raise FriendlyJSONError(_("The JSON box is empty. Paste some JSON or upload a .json file."))
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        hint = e.msg
        for key, friendly in _FRIENDLY:
            if e.msg.startswith(key):
                hint = _(friendly)
                break
        lines = text.splitlines() or [""]
        line_text = lines[e.lineno - 1] if 0 < e.lineno <= len(lines) else ""
        message = _("Line %(line)s, column %(col)s: %(hint)s") % {
            "line": e.lineno, "col": e.colno, "hint": hint,
        }
        raise FriendlyJSONError(message, e.lineno, e.colno, line_text)


def pretty(data):
    return json.dumps(data, ensure_ascii=False, indent=2)
