"""My Enrollments (courses -> modules -> lessons) and the Study Module pages."""
from django.contrib import messages
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from catalog.models import Course, Module, Step
from enrollment.models import ClassSession, Group, StepCompletion

from .access import annotate_modules, course_progress, step_statuses
from .calendar_utils import CalEvent, build_month_calendar, upcoming_events


def _student_or_redirect(request):
    if getattr(request.user, "role", None) != "student":
        return None
    return request.user.student


def _student_calendar(student, today):
    events = []
    for g in student.class_groups.select_related("class_session__course"):
        cs = g.class_session
        events.append(CalEvent(when=cs.start_date, title=cs.name, meta=f"Live session · {cs.course.name}",
                               kind="live", link=cs.join_link))
    for m in student.meetups.exclude(scheduled_time=None).select_related("coach"):
        coach_name = m.coach.display_name if m.coach else "your coach"
        events.append(CalEvent(when=m.scheduled_time, title="Coach meetup", meta=f"Meetup with {coach_name}",
                               kind="meetup", link=m.join_link))
    weeks, month_label = build_month_calendar(today, events)
    return {"cal_weeks": weeks, "cal_month_label": month_label, "upcoming": upcoming_events(today, events)}


@login_required
def enrollments(request):
    """Requirement #9: 'My Enrollments' is the student's home - a list of their courses."""
    student = _student_or_redirect(request)
    if student is None:
        return redirect("dashboard")

    courses = list(Course.objects.filter(pk__in=student.course_ids()).order_by("name"))
    groups = {g.class_session.course_id: g for g in
              student.class_groups.select_related("class_session__teacher", "coach")}
    total_done = total_steps = 0
    for c in courses:
        c.progress = course_progress(student, c)
        modules = annotate_modules(student, c)
        c.module_count = len(modules)
        c.current_module = next((m for m in modules if m.state == "current"), None)
        c.group = groups.get(c.pk)
        total_done += c.progress["approved"]
        total_steps += c.progress["total"]

    context = {
        "student": student, "courses": courses,
        "total_done": total_done, "total_steps": total_steps,
        "overall": round(total_done / total_steps * 100) if total_steps else 0,
        "has_coach": student.class_groups.exclude(coach=None).exists(),
        **_student_calendar(student, timezone.localdate()),
    }
    return render(request, "portal/enrollments.html", context)


@login_required
def course_detail(request, course_id):
    """Courses -> modules. Modules after the current one are locked (#10)."""
    student = _student_or_redirect(request)
    if student is None:
        return redirect("study_module_course", course_id=course_id)
    if course_id not in student.course_ids():
        messages.error(request, "You aren't enrolled in that course.")
        return redirect("enrollments")
    course = get_object_or_404(Course, pk=course_id)
    modules = annotate_modules(student, course)
    return render(request, "portal/course_detail.html", {
        "course": course, "modules": modules, "progress": course_progress(student, course),
    })


@login_required
def module_detail(request, module_id):
    """Module -> its lessons, and each lesson's steps listed by NAME only (#7)."""
    student = _student_or_redirect(request)
    module = get_object_or_404(Module.objects.select_related("course"), pk=module_id)
    if student is None:
        return redirect("study_module_course", course_id=module.course_id)
    if module.course_id not in student.course_ids():
        messages.error(request, "You aren't enrolled in that course.")
        return redirect("enrollments")

    modules = annotate_modules(student, module.course)
    this = next(m for m in modules if m.pk == module.pk)
    if this.state == "locked":
        messages.error(request, f"“{module.name}” is locked — finish the current module first.")
        return redirect("course_detail", course_id=module.course_id)

    statuses = step_statuses(student, module.course)
    lessons = list(this.lessons.all())
    for lesson in lessons:
        lesson.step_list = list(lesson.steps.all())
        for s in lesson.step_list:
            s.my_status = statuses.get(s.id, "")
        lesson.done = sum(1 for s in lesson.step_list if s.my_status in ("approved", "pending"))
    idx = modules.index(this)
    return render(request, "portal/module_detail.html", {
        "module": this, "course": module.course, "lessons": lessons,
        "next_module": modules[idx + 1] if idx + 1 < len(modules) else None,
    })


# ---------------------------------------------------------------- Study Module (#4)

def _visible_courses(user):
    role = getattr(user, "role", None)
    if role == "student":
        return Course.objects.filter(pk__in=user.student.course_ids())
    if role == "teacher":
        return Course.objects.filter(class_sessions__teacher=user.teacher).distinct()
    if role == "coach":
        return Course.objects.filter(
            Q(class_sessions__groups__coach=user.coach) | Q(class_sessions__invites__created_by=user)
        ).distinct()
    return Course.objects.all()   # admins


@login_required
def study_module(request):
    courses = list(_visible_courses(request.user).distinct().order_by("name"))
    if len(courses) == 1:
        return redirect("study_module_course", course_id=courses[0].pk)
    for c in courses:
        c.module_count = c.modules.count()
        c.step_count = Step.objects.filter(lesson__module__course=c).count()
    return render(request, "portal/study_module.html", {"courses": courses})


@login_required
def study_module_course(request, course_id):
    """The course programme: description, module/lesson structure and what each
    lesson contains (counts per step type) - no step text is shown."""
    course = get_object_or_404(_visible_courses(request.user).distinct(), pk=course_id)
    modules = list(course.modules.order_by("order", "id").prefetch_related("lessons__steps"))
    totals = {t: 0 for t, _ in Step.StepType.choices}
    for m in modules:
        for lesson in m.lessons.all():
            counts = {t: 0 for t, _ in Step.StepType.choices}
            for s in lesson.steps.all():
                counts[s.step_type] += 1
                totals[s.step_type] += 1
            lesson.counts = counts
            lesson.step_total = sum(counts.values())
    sessions = ClassSession.objects.filter(course=course).select_related("teacher").order_by("start_date")
    states = {}
    if getattr(request.user, "role", None) == "student":
        states = {m.pk: m.state for m in annotate_modules(request.user.student, course)}
    for m in modules:
        m.state = states.get(m.pk, "")
    return render(request, "portal/study_module_course.html", {
        "course": course, "modules": modules, "totals": totals,
        "total_steps": sum(totals.values()),
        "lesson_count": sum(m.lessons.count() for m in modules),
        "sessions": sessions,
        "type_labels": dict(Step.StepType.choices),
    })
