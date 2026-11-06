"""Adds the "Critical Thinking Crash Course" (Module 1 → Lesson 1 → 4 steps) and
enrols every student in it.

    python3 manage.py add_critical_thinking_course

Safe to run again: nothing is duplicated. Existing steps are left as they are
(so edits made in the admin are kept) unless you pass --update, which rewrites
the step texts from data/critical_thinking_lesson1.json. Students who join later
are added the next time you run it.
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from catalog.models import Course, Lesson, Module, Resource, Step
from enrollment.models import ClassSession, Group
from users.models import Student, Teacher

DATA_FILE = Path(__file__).resolve().parent / "data" / "critical_thinking_lesson1.json"


class Command(BaseCommand):
    help = "Create the Critical Thinking Crash Course (Module 1, Lesson 1) and enrol all students."

    def add_arguments(self, parser):
        parser.add_argument("--update", action="store_true",
                            help="Overwrite existing step titles/texts/videos with the ones in the JSON file.")

    @transaction.atomic
    def handle(self, *args, **opts):
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        c = data["course"]

        course, created = Course.objects.get_or_create(
            number=c["number"], name=c["name"], defaults={"description": c["description"]})
        self.stdout.write(f"Course: {course.name} (id {course.id}) {'created' if created else 'already exists'}")

        m = data["module"]
        module, _ = Module.objects.get_or_create(
            course=course, order=m["order"], defaults={"name": m["name"], "description": m["description"]})
        l = data["lesson"]
        lesson, _ = Lesson.objects.get_or_create(
            module=module, order=l["order"], defaults={"name": l["name"], "description": l["description"]})
        self.stdout.write(f"  {module.name}  →  {lesson.name}")

        video_dir = Path(settings.MEDIA_ROOT) / "step_videos"
        for s in data["steps"]:
            video = ""
            if s["video"]:
                if (video_dir / s["video"]).is_file():
                    video = f"step_videos/{s['video']}"
                else:
                    self.stderr.write(self.style.WARNING(f"  ! video file missing: media/step_videos/{s['video']}"))
            fields = {"title": s["title"], "step_type": s["step_type"], "body": s["body"], "video_file": video}
            step, made = Step.objects.get_or_create(lesson=lesson, order=s["order"], defaults=fields)
            if not made and opts["update"]:
                for k, v in fields.items():
                    setattr(step, k, v)
                step.save()
            # The answer key is kept in the step's Resource - only visible in the admin, never to students.
            Resource.objects.update_or_create(
                step=step, defaults={"resource_type": Resource.ResourceType.TEXT,
                                     "body": f"Answer key: {s['answer_key']}"})
            self.stdout.write(f"    step {step.order}: {step.title}  [{step.step_type}{', video' if step.video_file else ''}]"
                              f"  {'created' if made else ('updated' if opts['update'] else 'kept')}")

        # Students get a course through a class (Group). Every class needs a teacher.
        teacher = Teacher.objects.order_by("id").first()
        cs_data = data["class_session"]
        class_session = None
        if teacher:
            class_session, _ = ClassSession.objects.get_or_create(
                course=course, name=cs_data["name"],
                defaults={"teacher": teacher, "description": cs_data["description"], "start_date": timezone.now()})
            self.stdout.write(f"Class: {class_session.name} (teacher: {class_session.teacher})")
        else:
            self.stderr.write(self.style.WARNING(
                "No teacher exists yet, so no class was created. Students without a course get it as "
                "their enrolled course only. Create a teacher and run this command again."))

        added = enrolled = 0
        for student in Student.objects.all():
            if class_session:
                _, g = Group.objects.get_or_create(class_session=class_session, student=student,
                                                   defaults={"name": course.name})
                added += g
            if not student.enrolled_course_id:      # never replaces a course a student already has
                student.enrolled_course = course
                student.save(update_fields=["enrolled_course"])
                enrolled += 1
        total = Student.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f"Done. {total} students can open the course "
            f"({added} newly added to the class, {enrolled} got it as their main course)."))
