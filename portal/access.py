"""Who may open which course / module / step.

Rules (new requirements #9 and #10):
- A student sees the courses of the classes they joined through an invite link
  (plus their enrolled course).
- Inside a course, modules open one at a time. The *current* module is the
  first one that still has unfinished steps: every lesson in it is available.
  Modules after it stay locked until it is finished. Modules already finished
  stay open for review.
- A step counts as finished once it is completed (video/text) or its answer is
  submitted (quiz/practice: pending or approved). A rejected answer counts as
  unfinished until it is resubmitted.
"""
from catalog.models import Step
from enrollment.models import StepCompletion

FINISHED = {StepCompletion.Status.APPROVED, StepCompletion.Status.PENDING}


def step_statuses(student, course):
    return dict(
        student.completed_steps.filter(step__lesson__module__course=course).values_list("step_id", "status")
    )


def annotate_modules(student, course):
    """Returns the course's modules (in order) with these extra attributes:
    state ('completed' | 'current' | 'locked'), total_steps, finished_steps,
    approved_steps, percent, is_open."""
    modules = list(course.modules.order_by("order", "id").prefetch_related("lessons__steps"))
    statuses = step_statuses(student, course)
    current_found = False
    for m in modules:
        steps = [s for lesson in m.lessons.all() for s in lesson.steps.all()]
        m.total_steps = len(steps)
        m.finished_steps = sum(1 for s in steps if statuses.get(s.id) in FINISHED)
        m.approved_steps = sum(1 for s in steps if statuses.get(s.id) == StepCompletion.Status.APPROVED)
        m.percent = round(m.approved_steps / m.total_steps * 100) if m.total_steps else 100
        if current_found:
            m.state = "locked"
        elif m.finished_steps >= m.total_steps:
            m.state = "completed"
        else:
            m.state = "current"
            current_found = True
        m.is_open = m.state != "locked"
    return modules


def module_state(student, module):
    for m in annotate_modules(student, module.course):
        if m.pk == module.pk:
            return m.state
    return "locked"


def student_can_open_step(student, step):
    """(allowed, reason)"""
    course_id = step.lesson.module.course_id
    if course_id not in student.course_ids():
        return False, "That step isn't part of your courses."
    if module_state(student, step.lesson.module) == "locked":
        return False, "That module is locked — finish the current module first."
    return True, ""


def course_progress(student, course):
    total = Step.objects.filter(lesson__module__course=course).count()
    statuses = step_statuses(student, course)
    approved = sum(1 for s in statuses.values() if s == StepCompletion.Status.APPROVED)
    return {
        "total": total, "approved": approved,
        "percent": round(approved / total * 100, 1) if total else 0.0,
    }
