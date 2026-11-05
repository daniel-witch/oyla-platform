"""Tests for the lab requirements: 3 access levels (guest / member /
administrator), pagination, filtering, the combined /api/dashboard/ resource,
and full CRUD + list on users and messages."""
from django.test import TestCase
from rest_framework.test import APIClient

from catalog.models import Course, Module, Step, Lesson
from users.models import User, Student, Teacher


class LabRequirementsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("adm", "adm@example.com", "Adm-Pass-2026")
        self.c1 = Course.objects.create(name="Logic", number="L1")
        self.c2 = Course.objects.create(name="Algebra", number="A1")
        self.m1 = Module.objects.create(course=self.c1, name="M1", order=1)
        self.m2 = Module.objects.create(course=self.c2, name="M2", order=1)
        self.l1 = Lesson.objects.create(module=self.m1, name="L", order=1)
        Step.objects.create(lesson=self.l1, title="Q", step_type="quiz", order=1)
        Step.objects.create(lesson=self.l1, title="T", step_type="text", order=2)
        self.stu = Student.objects.create_user("stu", "stu@example.com", "Stu-Pass-2026")
        self.stu.enrolled_course = self.c1
        self.stu.save()
        self.api = APIClient()

    def as_(self, user):
        self.api.force_authenticate(user)
        return self.api

    # --- roles ---
    def test_guest_can_browse_catalog_but_nothing_else(self):
        g = APIClient()
        self.assertEqual(g.get("/api/courses/").status_code, 200)
        self.assertEqual(g.get("/api/lessons/").status_code, 200)
        self.assertEqual(g.get("/api/announcements/").status_code, 200)
        self.assertEqual(g.get("/api/students/").status_code, 401)
        self.assertEqual(g.get("/api/dashboard/").status_code, 401)
        self.assertEqual(g.post("/api/courses/", {"name": "x"}, format="json").status_code, 401)

    def test_access_levels(self):
        self.assertEqual(self.as_(self.stu).get("/api/auth/me/").json()["access_level"], "member")
        self.assertEqual(self.as_(self.admin).get("/api/auth/me/").json()["access_level"], "administrator")

    # --- pagination ---
    def test_pagination(self):
        r = self.as_(self.admin).get("/api/courses/?limit=1&offset=1").json()
        self.assertEqual(r["count"], 2)
        self.assertEqual(len(r["results"]), 1)
        self.assertIsNotNone(r["previous"])
        self.assertIsInstance(self.api.get("/api/courses/").json(), list)  # no ?limit -> plain list

    # --- filtering ---
    def test_filtering_search_and_ordering(self):
        a = self.as_(self.admin)
        mods = a.get(f"/api/modules/?course={self.c1.pk}").json()
        self.assertEqual([m["id"] for m in mods], [self.m1.pk])
        self.assertEqual([c["name"] for c in a.get("/api/courses/?search=alg").json()], ["Algebra"])
        self.assertEqual([c["name"] for c in a.get("/api/courses/?ordering=name").json()], ["Algebra", "Logic"])
        self.assertEqual({s["step_type"] for s in a.get(f"/api/steps/?course={self.c1.pk}&step_type=quiz").json()}, {"quiz"})
        self.assertEqual(a.get("/api/modules/?course=abc").status_code, 400)

    # --- combined resource ---
    def test_dashboard_combines_entities(self):
        d = self.as_(self.stu).get("/api/dashboard/").json()
        for key in ("profile", "access_level", "unread_messages", "latest_announcements", "courses", "groups"):
            self.assertIn(key, d)
        self.assertEqual(d["courses"][0]["name"], "Logic")
        self.assertIn("percent", d["courses"][0]["progress"])
        self.assertIn("totals", self.as_(self.admin).get("/api/dashboard/").json())

    # --- 5 methods on users and messages ---
    def test_users_full_crud_admin_only(self):
        a = self.as_(self.admin)
        r = a.post("/api/users/", {"username": "u1", "password": "Str0ng-Pass-2026"}, format="json")
        self.assertEqual(r.status_code, 201)
        uid = r.json()["id"]
        self.assertTrue(User.objects.get(pk=uid).check_password("Str0ng-Pass-2026"))
        self.assertEqual(a.get(f"/api/users/{uid}/").status_code, 200)
        self.assertEqual(a.put(f"/api/users/{uid}/", {"username": "u1", "first_name": "X"}, format="json").status_code, 200)
        self.assertEqual(a.patch(f"/api/users/{uid}/", {"last_name": "Y"}, format="json").status_code, 200)
        self.assertEqual(self.as_(self.stu).delete(f"/api/users/{uid}/").status_code, 403)
        self.assertEqual(self.as_(self.admin).delete(f"/api/users/{uid}/").status_code, 204)

    def test_messages_edit_by_sender_until_read(self):
        t = Teacher.objects.create_user("tch", "t@example.com", "Tch-Pass-2026")
        s = self.as_(self.stu)
        mid = s.post("/api/messages/", {"recipient": t.pk, "subject": "Hi", "body": "a"}, format="json").json()["id"]
        self.assertEqual(s.patch(f"/api/messages/{mid}/", {"body": "b"}, format="json").status_code, 200)
        self.assertEqual(self.as_(t).patch(f"/api/messages/{mid}/", {"body": "c"}, format="json").status_code, 403)
        self.as_(t).get(f"/api/messages/{mid}/")  # recipient reads it
        self.assertEqual(self.as_(self.stu).patch(f"/api/messages/{mid}/", {"body": "d"}, format="json").status_code, 403)
