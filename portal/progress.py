"""One place that calculates a student's progress, used by the dashboard's
live updates (JSON) and returned after every step save."""
from collections import defaultdict

from catalog.models import Step
from enrollment.models import StepCompletion


def build_progress(student):
    course = student.enrolled_course
    if not course:
        return {"course_id": None, "progress": 0, "completed_count": 0, "total_steps": 0,
                "remaining_count": 0, "modules": {}, "steps": {}}

    step_rows = list(Step.objects.filter(lesson__module__course=course).values_list("id", "lesson__module_id"))
    step_ids = {sid for sid, _ in step_rows}
    statuses = {
        sid: status for sid, status in
        student.completed_steps.filter(step_id__in=step_ids).values_list("step_id", "status")
    }
    per_module = defaultdict(lambda: {"completed": 0, "total": 0})
    for sid, mid in step_rows:
        per_module[mid]["total"] += 1
        if statuses.get(sid) == StepCompletion.Status.APPROVED:
            per_module[mid]["completed"] += 1
    for m in per_module.values():
        m["percent"] = round(m["completed"] / m["total"] * 100) if m["total"] else 0

    completed = sum(1 for s in statuses.values() if s == StepCompletion.Status.APPROVED)
    total = len(step_rows)
    return {
        "course_id": course.pk,
        "progress": student.view_progress(),
        "completed_count": completed,
        "total_steps": total,
        "remaining_count": total - completed,
        "modules": {str(mid): data for mid, data in per_module.items()},
        "steps": {str(sid): status for sid, status in statuses.items()},
    }
