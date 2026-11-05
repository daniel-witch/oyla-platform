"""Import / export a whole course (Course → Module → Lesson → Step → Resource) as JSON."""
from django.db import transaction

from catalog.models import Course, Module, Lesson, Step, Resource
from .models import JsonRecord
from .serializers import CourseImportSerializer, readable_errors


class CourseImportError(Exception):
    def __init__(self, messages):
        super().__init__("; ".join(messages))
        self.messages = messages


def validate_course_json(raw):
    """Validate the uploaded structure. Returns clean data or raises CourseImportError."""
    if not isinstance(raw, dict):
        raise CourseImportError(['The course JSON must be one object that starts with { and has "name" and "modules".'])
    raw = dict(raw)
    raw.pop("update_existing", None)
    ser = CourseImportSerializer(data=raw)
    if not ser.is_valid():
        raise CourseImportError(readable_errors(ser.errors))
    return ser.validated_data


def import_course(raw, update_existing=False, user=None):
    """Create (or replace) a course from JSON. All-or-nothing thanks to transaction.atomic().

    Returns {"course_id", "created", "modules", "lessons", "steps", "resources", "record_id"}.
    """
    if isinstance(raw, dict) and "update_existing" in raw:
        update_existing = update_existing or bool(raw.get("update_existing"))
    data = validate_course_json(raw)
    counts = {"modules": 0, "lessons": 0, "steps": 0, "resources": 0}

    with transaction.atomic():
        course = None
        if update_existing and data["number"]:
            course = Course.objects.filter(number=data["number"]).first()
        created = course is None
        if created:
            course = Course.objects.create(
                name=data["name"], number=data["number"], description=data["description"],
            )
        else:
            course.name = data["name"]
            course.description = data["description"]
            course.save()
            course.modules.all().delete()   # cascades to lessons/steps/resources

        for m in data["modules"]:
            module = Module.objects.create(
                course=course, name=m["name"], description=m["description"], order=m["order"],
            )
            counts["modules"] += 1
            for l in m["lessons"]:
                lesson = Lesson.objects.create(
                    module=module, name=l["name"], description=l["description"], order=l["order"],
                )
                counts["lessons"] += 1
                for s in l["steps"]:
                    step = Step.objects.create(
                        lesson=lesson, title=s.get("title", ""), step_type=s["step_type"], body=s["body"],
                        link=s["link"], order=s["order"],
                    )
                    counts["steps"] += 1
                    r = s.get("resource")
                    if r:
                        Resource.objects.create(
                            step=step, resource_type=r["resource_type"],
                            body=r["body"], link=r["link"],
                        )
                        counts["resources"] += 1

        # Keep the original upload as history.
        record = JsonRecord.objects.create(
            title=f"Course import: {course.name}"[:255],
            category="course-import",
            data=raw,
            created_by=user if (user and user.is_authenticated) else None,
        )

    return {"course_id": course.pk, "created": created, **counts, "record_id": record.pk}


def export_course(course):
    """Same structure the importer accepts, so export → import round-trips."""
    modules = []
    for m in course.modules.all().prefetch_related("lessons__steps__resource"):
        lessons = []
        for l in m.lessons.all():
            steps = []
            for s in l.steps.all():
                step = {"title": s.title, "step_type": s.step_type, "body": s.body, "link": s.link, "order": s.order}
                try:
                    r = s.resource
                    step["resource"] = {"resource_type": r.resource_type, "body": r.body, "link": r.link}
                except Resource.DoesNotExist:
                    pass
                steps.append(step)
            lessons.append({"name": l.name, "description": l.description, "order": l.order, "steps": steps})
        modules.append({"name": m.name, "description": m.description, "order": m.order, "lessons": lessons})
    return {"name": course.name, "number": course.number, "description": course.description, "modules": modules}
