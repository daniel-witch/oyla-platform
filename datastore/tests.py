import json
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from catalog.models import Course, Module, Lesson, Step, Resource
from enrollment.models import ClassSession, Group
from users.models import Student, Teacher, Coach
from .models import JsonRecord

COURSE_JSON = {
    "name": "Critical Thinking Math", "number": "CT-101", "description": "Курс туралы",
    "modules": [
        {"name": "Ratios & Proportional Relationships", "description": "Қатынастар", "order": 1,
         "lessons": [
             {"name": "Lesson 1.1", "description": "Intro", "order": 1,
              "steps": [
                  {"step_type": "video", "body": "Watch", "link": "https://youtube.com/watch?v=abc", "order": 1,
                   "resource": {"resource_type": "video", "body": "", "link": "https://youtube.com/watch?v=abc"}},
                  {"step_type": "quiz", "body": "2:3 = 4:? A) 5 B) 6", "order": 2},
              ]},
             {"name": "Lesson 1.2", "description": "", "order": 2,
              "steps": [{"step_type": "text", "body": "Read", "order": 1}]},
         ]},
        {"name": "Module 2", "description": "", "order": 2, "lessons": []},
    ],
}


class Base(TestCase):
    def setUp(self):
        self.s1 = Student.objects.create_user("stud1", password="pass12345")
        self.s2 = Student.objects.create_user("stud2", password="pass12345")
        self.teacher = Teacher.objects.create_user("teach", password="pass12345")
        self.other_teacher = Teacher.objects.create_user("teach2", password="pass12345")
        self.coach = Coach.objects.create_user("coach", password="pass12345")
        course = Course.objects.create(name="C")
        session = ClassSession.objects.create(course=course, teacher=self.teacher, name="10A",
                                              start_date=timezone.now())
        Group.objects.create(class_session=session, student=self.s1, coach=self.coach)

    def api(self, user):
        c = APIClient()
        token, _ = Token.objects.get_or_create(user=user)
        c.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return c


class JsonRecordApiTests(Base):
    def test_student_crud_own_records(self):
        c = self.api(self.s1)
        r = c.post("/api/json-records/", {"title": "Quiz", "category": "quiz",
                                          "data": {"name": "Aruzhan", "answers": ["B", "D"]}}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        pk = r.data["id"]
        self.assertEqual(JsonRecord.objects.get(pk=pk).created_by_id, self.s1.pk)

        r = c.get("/api/json-records/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 1)
        self.assertEqual(c.get("/api/json-records/?category=quiz").data[0]["id"], pk)
        self.assertEqual(len(c.get("/api/json-records/?search=nothing").data), 0)

        r = c.patch(f"/api/json-records/{pk}/", {"data": {"name": "Aruzhan", "answers": ["A"]}}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(JsonRecord.objects.get(pk=pk).data["answers"], ["A"])

        r = c.get(f"/api/json-records/{pk}/download/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertEqual(json.loads(r.content)["answers"], ["A"])

        self.assertEqual(c.delete(f"/api/json-records/{pk}/").status_code, 204)
        self.assertFalse(JsonRecord.objects.filter(pk=pk).exists())

    def test_student_cannot_see_other_students_record(self):
        rec = JsonRecord.objects.create(title="secret", data={"a": 1}, created_by=self.s2)
        c = self.api(self.s1)
        self.assertEqual(c.get(f"/api/json-records/{rec.pk}/").status_code, 404)
        self.assertEqual(c.delete(f"/api/json-records/{rec.pk}/").status_code, 404)
        self.assertEqual(c.get("/api/json-records/").data, [])

    def test_teacher_and_coach_see_their_students_records(self):
        mine = JsonRecord.objects.create(title="s1", data={"a": 1}, created_by=self.s1)
        JsonRecord.objects.create(title="s2", data={"a": 2}, created_by=self.s2)  # not in their class
        for user in (self.teacher, self.coach):
            ids = [r["id"] for r in self.api(user).get("/api/json-records/").data]
            self.assertEqual(ids, [mine.pk])
        self.assertEqual(self.api(self.other_teacher).get("/api/json-records/").data, [])

    def test_teacher_can_comment_but_not_edit(self):
        rec = JsonRecord.objects.create(title="s1", data={"a": 1}, created_by=self.s1)
        t = self.api(self.teacher)
        r = t.post(f"/api/json-records/{rec.pk}/comment/", {"teacher_comment": "Жақсы!"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(JsonRecord.objects.get(pk=rec.pk).teacher_comment, "Жақсы!")
        self.assertEqual(t.patch(f"/api/json-records/{rec.pk}/", {"title": "x"}, format="json").status_code, 403)
        # student can't comment
        r = self.api(self.s1).post(f"/api/json-records/{rec.pk}/comment/", {"teacher_comment": "x"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_invalid_json_rejected_with_line_number(self):
        c = self.api(self.s1)
        bad = '{\n  "name": "Aruzhan"\n  "age": 15\n}'
        r = c.post("/api/json-records/", {"title": "t", "data": bad}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Line 3", str(r.data["data"]))
        self.assertIn("comma", str(r.data["data"]))
        # a raw broken request body
        r = c.post("/api/json-records/", data='{"title": "t", "data": {"a": 1,}}', content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("line 1", str(r.data).lower())
        # not an object/list
        r = c.post("/api/json-records/", {"title": "t", "data": 5}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_size_and_count_limits(self):
        c = self.api(self.s1)
        r = c.post("/api/json-records/", {"title": "big", "data": {"x": "a" * 1_000_001}}, format="json")
        self.assertEqual(r.status_code, 400)
        JsonRecord.objects.bulk_create([JsonRecord(title=str(i), data={}, created_by=self.s1) for i in range(200)])
        r = c.post("/api/json-records/", {"title": "201", "data": {}}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("maximum", r.data["detail"])

    def test_requires_login(self):
        self.assertEqual(APIClient().get("/api/json-records/").status_code, 401)


class CourseImportTests(Base):
    def test_student_gets_403(self):
        r = self.api(self.s1).post("/api/import/course/", COURSE_JSON, format="json")
        self.assertEqual(r.status_code, 403)
        self.client.force_login(self.s1)
        self.assertEqual(self.client.get("/data/import-course/").status_code, 403)

    def test_import_creates_correct_counts(self):
        before = Course.objects.count()
        r = self.api(self.teacher).post("/api/import/course/", COURSE_JSON, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.data["modules"], r.data["lessons"], r.data["steps"], r.data["resources"]), (2, 2, 3, 1))
        course = Course.objects.get(pk=r.data["course_id"])
        self.assertEqual(Course.objects.count(), before + 1)
        self.assertEqual(course.description, "Курс туралы")
        self.assertEqual(Step.objects.filter(lesson__module__course=course).count(), 3)
        self.assertTrue(JsonRecord.objects.filter(category="course-import", created_by=self.teacher).exists())

    def test_update_existing_replaces_content(self):
        c = self.api(self.coach)
        first = c.post("/api/import/course/", COURSE_JSON, format="json").data
        smaller = dict(COURSE_JSON, modules=COURSE_JSON["modules"][:1], update_existing=True)
        r = c.post("/api/import/course/", smaller, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["course_id"], first["course_id"])
        self.assertEqual(Module.objects.filter(course_id=first["course_id"]).count(), 1)

    def test_bad_step_type_gives_clear_message(self):
        bad = json.loads(json.dumps(COURSE_JSON))
        bad["modules"][0]["lessons"][1]["steps"][0]["step_type"] = "vidoe"
        r = self.api(self.teacher).post("/api/import/course/", bad, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Module 1 → Lesson 2 → Step 1 → step_type", r.data["errors"][0])

    def test_failing_import_rolls_back_fully(self):
        counts = lambda: (Course.objects.count(), Module.objects.count(), Lesson.objects.count(),
                          Step.objects.count(), Resource.objects.count(), JsonRecord.objects.count())
        before = counts()
        with mock.patch("datastore.importer.Resource.objects.create", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                from datastore.importer import import_course
                import_course(COURSE_JSON, user=self.teacher)
        self.assertEqual(counts(), before)

    def test_export_import_round_trip(self):
        t = self.api(self.teacher)
        cid = t.post("/api/import/course/", COURSE_JSON, format="json").data["course_id"]
        exported = t.get(f"/api/courses/{cid}/export/").data
        self.assertEqual(exported["modules"][0]["lessons"][0]["steps"][0]["resource"]["resource_type"], "video")
        copy = dict(exported, number="CT-102")
        cid2 = t.post("/api/import/course/", copy, format="json").data["course_id"]
        exported2 = t.get(f"/api/courses/{cid2}/export/").data
        self.assertEqual(dict(exported2, number="CT-101"), dict(exported))


class WebPageTests(Base):
    def test_student_web_flow(self):
        self.client.force_login(self.s1)
        self.assertEqual(self.client.get("/data/").status_code, 200)
        self.assertEqual(self.client.get("/data/new/").status_code, 200)
        r = self.client.post("/data/new/", {"title": "Notes", "category": "notes",
                                            "json_text": '{"a": 1,\n "b": [1, 2]\n "c": 3}'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Line 3")
        r = self.client.post("/data/new/", {"title": "Notes", "category": "notes", "json_text": '{"a": "Сәлем"}'})
        rec = JsonRecord.objects.get(title="Notes")
        self.assertRedirects(r, f"/data/{rec.pk}/")
        self.assertContains(self.client.get(f"/data/{rec.pk}/"), "Сәлем")
        self.assertEqual(self.client.get(f"/data/{rec.pk}/edit/").status_code, 200)
        self.assertEqual(self.client.get(f"/data/{rec.pk}/download/").status_code, 200)
        self.assertRedirects(self.client.post(f"/data/{rec.pk}/delete/"), "/data/")
        self.assertFalse(JsonRecord.objects.filter(pk=rec.pk).exists())

    def test_web_file_upload(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.s1)
        f = SimpleUploadedFile("a.json", '{"from": "file"}'.encode(), content_type="application/json")
        self.client.post("/data/new/", {"title": "F", "json_text": "", "json_file": f})
        self.assertEqual(JsonRecord.objects.get(title="F").data, {"from": "file"})

    def test_teacher_web_comment_and_import(self):
        rec = JsonRecord.objects.create(title="s1 work", data={"a": 1}, created_by=self.s1)
        self.client.force_login(self.teacher)
        r = self.client.get("/data/")
        self.assertContains(r, "s1 work")
        self.client.post(f"/data/{rec.pk}/", {"teacher_comment": "Well done"})
        self.assertEqual(JsonRecord.objects.get(pk=rec.pk).teacher_comment, "Well done")
        self.assertEqual(self.client.get(f"/data/{rec.pk}/edit/").status_code, 403)
        r = self.client.post("/data/import-course/", {"json_text": json.dumps(COURSE_JSON)})
        self.assertContains(r, "Course created")
        self.client.force_login(self.s2)
        self.assertEqual(self.client.get(f"/data/{rec.pk}/").status_code, 404)
