"""Tests for the 12 new requirements."""
import shutil
import tempfile
from datetime import timedelta
from io import BytesIO

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from catalog.models import Course, Lesson, Module, Step
from communication.models import Announcement, Message
from enrollment.models import ClassInvite, ClassSession, Feedback, Group, StepCompletion
from users.models import Coach, Student, Teacher, User

TMP_MEDIA = tempfile.mkdtemp()


def png_bytes():
    buf = BytesIO()
    Image.new("RGB", (8, 8), (30, 90, 200)).save(buf, "PNG")
    return buf.getvalue()


class Base(TestCase):
    def setUp(self):
        self.course = Course.objects.create(name="Critical Thinking", number="CT101")
        self.m1 = Module.objects.create(course=self.course, name="Module One", order=1)
        self.m2 = Module.objects.create(course=self.course, name="Module Two", order=2)
        l1 = Lesson.objects.create(module=self.m1, name="Lesson A", order=1)
        l2 = Lesson.objects.create(module=self.m1, name="Lesson B", order=2)
        l3 = Lesson.objects.create(module=self.m2, name="Lesson C", order=1)
        self.s1 = Step.objects.create(lesson=l1, title="What is an argument?", step_type="text",
                                      body="SECRET BODY TEXT", order=1)
        self.s2 = Step.objects.create(lesson=l2, title="Quick quiz", step_type="quiz", body="Q?", order=1)
        self.s3 = Step.objects.create(lesson=l3, title="Module two reading", step_type="text", body="later", order=1)
        self.teacher = Teacher.objects.create_user("teach", password="Pass-12345", email="t@example.com",
                                                   first_name="Tom")
        self.coach = Coach.objects.create_user("coachy", password="Pass-12345", email="c@example.com")
        self.student = Student.objects.create_user("stud", password="Pass-12345", email="s@example.com",
                                                   first_name="Sara")
        self.session = ClassSession.objects.create(course=self.course, teacher=self.teacher, name="Fall cohort",
                                                   start_date=timezone.now())

    def join(self, student=None):
        inv = ClassInvite.objects.create(class_session=self.session, created_by=self.teacher, coach=self.coach)
        inv.join(student or self.student)
        return inv


class PersonalIdTests(Base):   # 6
    def test_each_role_gets_its_own_id(self):
        self.assertEqual(self.student.student_code, f"STU-{self.student.pk:05d}")
        self.assertEqual(self.teacher.teacher_code, f"TCH-{self.teacher.pk:05d}")
        self.assertEqual(self.coach.coach_code, f"CCH-{self.coach.pk:05d}")
        self.assertEqual(User.objects.get(pk=self.student.pk).personal_id, self.student.student_code)


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class ProfileTests(Base):   # 1
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def test_avatar_popover_and_photo_upload(self):
        self.join()
        self.client.force_login(self.student)
        r = self.client.get("/enrollments/")
        self.assertContains(r, 'id="profile-pop"')
        self.assertContains(r, self.student.student_code)
        photo = SimpleUploadedFile("me.png", png_bytes(), content_type="image/png")
        r = self.client.post("/profile/", {"photo": photo, "first_name": "Sara", "last_name": "K",
                                           "email": "s@example.com"})
        self.assertRedirects(r, "/profile/")
        user = User.objects.get(pk=self.student.pk)
        self.assertTrue(user.photo.name.startswith("avatars/"))
        r = self.client.get("/enrollments/")
        self.assertContains(r, user.photo.url)
        self.assertEqual(self.client.get(user.photo.url).status_code, 200)


class NoUndoTests(Base):   # 2
    def test_api_student_cannot_delete_or_change_completion(self):
        self.join()
        c = StepCompletion.objects.create(student=self.student, step=self.s1)
        api = APIClient()
        api.force_authenticate(self.student)
        self.assertEqual(api.delete(f"/api/step-completions/{c.pk}/").status_code, 403)
        self.assertEqual(api.patch(f"/api/step-completions/{c.pk}/", {"answer": "x"}, format="json").status_code, 403)
        self.assertTrue(StepCompletion.objects.filter(pk=c.pk).exists())

    def test_submitted_quiz_cannot_be_resubmitted_unless_rejected(self):
        self.join()
        self.client.force_login(self.student)
        self.client.post(f"/steps/{self.s2.id}/", {"answer": "A"})
        r = self.client.post(f"/steps/{self.s2.id}/", {"answer": "B"}, HTTP_X_REQUESTED_WITH="fetch",
                             HTTP_ACCEPT="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(StepCompletion.objects.get(step=self.s2).answer, "A")
        StepCompletion.objects.filter(step=self.s2).update(status="rejected")
        self.client.post(f"/steps/{self.s2.id}/", {"answer": "B"})
        self.assertEqual(StepCompletion.objects.get(step=self.s2).answer, "B")


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class PasswordTests(Base):   # 3
    def test_user_panel_and_admin_panel(self):
        self.client.force_login(self.student)
        r = self.client.post("/password-change/", {"old_password": "Pass-12345", "new_password1": "Brand-New-77",
                                                   "new_password2": "Brand-New-77"})
        self.assertRedirects(r, "/password-change/done/")
        self.assertTrue(User.objects.get(pk=self.student.pk).check_password("Brand-New-77"))

        admin = User.objects.create_superuser("boss", "b@example.com", "Pass-12345")
        self.client.force_login(admin)
        url = f"/admin/users/student/{self.student.pk}/password/"
        self.assertEqual(self.client.get(url).status_code, 200)
        r = self.client.post(url, {"password1": "Admin-Set-88", "password2": "Admin-Set-88",
                                   "usable_password": "true"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(User.objects.get(pk=self.student.pk).check_password("Admin-Set-88"))
        # Add-student page in admin hashes the password
        r = self.client.post("/admin/users/student/add/", {"username": "newbie", "password1": "Admin-Set-88",
                                                           "password2": "Admin-Set-88", "usable_password": "true"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Student.objects.get(username="newbie").check_password("Admin-Set-88"))
        self.assertTrue(Student.objects.get(username="newbie").student_code.startswith("STU-"))


class StudyModuleTests(Base):   # 4
    def test_in_menu_and_shows_programme(self):
        self.join()
        self.client.force_login(self.student)
        r = self.client.get("/enrollments/")
        self.assertContains(r, 'href="/study-module/"')
        r = self.client.get("/study-module/", follow=True)
        self.assertContains(r, "Programme structure")
        self.assertContains(r, "Lesson A")
        self.assertNotContains(r, "SECRET BODY TEXT")
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(f"/study-module/{self.course.id}/"), "Module Two")


class InviteTests(Base):   # 5
    def test_join_only_through_link(self):
        self.client.force_login(self.student)
        # Not in a class -> can't open course
        self.assertRedirects(self.client.get(f"/enrollments/course/{self.course.id}/"), "/enrollments/")
        # Teacher creates a link
        self.client.force_login(self.teacher)
        self.client.post("/invites/", {"class_session": self.session.id, "coach": self.coach.id, "days": "7"})
        inv = ClassInvite.objects.get()
        self.assertContains(self.client.get("/invites/"), f"/join/{inv.token}/")
        # Student uses it
        self.client.force_login(self.student)
        r = self.client.get(f"/join/{inv.token}/")
        self.assertRedirects(r, f"/enrollments/course/{self.course.id}/")
        g = Group.objects.get(student=self.student)
        self.assertEqual((g.class_session, g.coach, g.invite), (self.session, self.coach, inv))
        inv.refresh_from_db()
        self.assertEqual(inv.uses, 1)

    def test_paste_code_box_and_coach_link(self):
        inv = ClassInvite.objects.create(class_session=self.session, created_by=self.coach)
        self.client.force_login(self.student)
        r = self.client.post("/join/", {"code": f"https://x.onrender.com/join/{inv.token}/"}, follow=True)
        self.assertContains(r, "You joined")
        self.assertEqual(Group.objects.get(student=self.student).coach, self.coach)

    def test_expired_and_used_up_links(self):
        inv = ClassInvite.objects.create(class_session=self.session, created_by=self.teacher,
                                         expires_at=timezone.now() - timedelta(minutes=1))
        self.client.force_login(self.student)
        r = self.client.get(f"/join/{inv.token}/", follow=True)
        self.assertContains(r, "expired")
        inv2 = ClassInvite.objects.create(class_session=self.session, created_by=self.teacher, max_uses=1)
        inv2.join(Student.objects.create_user("other", password="Pass-12345"))
        r = self.client.get(f"/join/{inv2.token}/", follow=True)
        self.assertContains(r, "maximum")
        self.assertFalse(Group.objects.filter(student=self.student).exists())

    def test_anonymous_user_is_sent_to_login_then_joins(self):
        inv = ClassInvite.objects.create(class_session=self.session, created_by=self.teacher)
        r = self.client.get(f"/join/{inv.token}/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])
        r = self.client.post(r["Location"], {"username": "stud", "password": "Pass-12345"})
        self.assertEqual(r["Location"], f"/join/{inv.token}/")

    def test_api_students_cannot_add_themselves_to_groups(self):
        api = APIClient()
        api.force_authenticate(self.student)
        r = api.post("/api/groups/", {"class_session": self.session.id, "student": self.student.id}, format="json")
        self.assertEqual(r.status_code, 403)
        api.force_authenticate(self.teacher)
        r = api.post("/api/invites/", {"class_session": self.session.id}, format="json")
        self.assertEqual(r.status_code, 201)
        token = r.json()["token"]
        self.assertIn(f"/join/{token}/", r.json()["join_url"])
        api.force_authenticate(self.student)
        r = api.post("/api/invites/join/", {"token": token}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(api.post("/api/invites/join/", {"token": token}, format="json").status_code, 200)


class NavigationAndLockingTests(Base):   # 7, 9, 10
    def test_enrollments_course_module_flow(self):
        self.join()
        self.client.force_login(self.student)
        self.assertRedirects(self.client.get("/"), "/enrollments/")
        r = self.client.get("/enrollments/")
        self.assertContains(r, "Critical Thinking")
        self.assertContains(r, f"/enrollments/course/{self.course.id}/")
        r = self.client.get(f"/enrollments/course/{self.course.id}/")
        self.assertContains(r, f"/enrollments/module/{self.m1.id}/")
        self.assertNotContains(r, f"/enrollments/module/{self.m2.id}/")   # locked: no link
        self.assertContains(r, "Locked")

    def test_only_step_names_are_listed(self):
        self.join()
        self.client.force_login(self.student)
        r = self.client.get(f"/enrollments/module/{self.m1.id}/")
        self.assertContains(r, "What is an argument?")
        self.assertContains(r, "Quick quiz")
        self.assertNotContains(r, "SECRET BODY TEXT")
        self.assertContains(self.client.get(f"/steps/{self.s1.id}/"), "SECRET BODY TEXT")

    def test_current_module_open_next_locked_until_finished(self):
        self.join()
        self.client.force_login(self.student)
        # every lesson of the current module is open
        self.assertEqual(self.client.get(f"/steps/{self.s2.id}/").status_code, 200)
        # next module locked (page and its steps)
        self.assertRedirects(self.client.get(f"/enrollments/module/{self.m2.id}/"),
                             f"/enrollments/course/{self.course.id}/")
        self.assertRedirects(self.client.get(f"/steps/{self.s3.id}/"), "/enrollments/")
        # finish module one -> module two opens, module one stays open for review
        self.client.post(f"/steps/{self.s1.id}/", {"action": "complete"})
        self.client.post(f"/steps/{self.s2.id}/", {"answer": "B"})
        self.assertEqual(self.client.get(f"/enrollments/module/{self.m2.id}/").status_code, 200)
        self.assertEqual(self.client.get(f"/steps/{self.s3.id}/").status_code, 200)
        self.assertEqual(self.client.get(f"/enrollments/module/{self.m1.id}/").status_code, 200)

    def test_api_my_enrollments_hides_locked_steps(self):
        self.join()
        api = APIClient()
        api.force_authenticate(self.student)
        data = api.get("/api/my/enrollments/").json()
        mods = data["courses"][0]["modules"]
        self.assertEqual([m["state"] for m in mods], ["current", "locked"])
        self.assertEqual(mods[0]["lessons"][0]["steps"][0]["name"], "What is an argument?")
        self.assertEqual(mods[1]["lessons"][0]["steps"], [])


class AnnouncementTests(Base):   # 8
    def test_newspaper_and_publishing(self):
        self.client.force_login(self.student)
        r = self.client.get("/announcements/")
        self.assertContains(r, "The Oyla Gazette")
        self.assertContains(r, "Welcome to Oyla Platform")   # starter guides from the migration
        self.assertRedirects(self.client.get("/announcements/new/"), "/announcements/")
        self.client.force_login(self.teacher)
        r = self.client.post("/announcements/new/", {"title": "Midterm on Friday", "category": "event",
                                                     "summary": "Room 204", "body": "Bring a pen."})
        a = Announcement.objects.get(title="Midterm on Friday")
        self.assertEqual(a.author, self.teacher.user_ptr)
        self.client.force_login(self.student)
        self.assertContains(self.client.get(f"/announcements/{a.id}/"), "Bring a pen.")
        self.assertContains(self.client.get("/announcements/?category=event"), "Midterm on Friday")


class FeedbackTests(Base):   # 11
    def test_both_directions(self):
        self.join()
        self.client.force_login(self.student)
        self.client.post("/feedback/", {"to": self.teacher.id, "content": "Great explanations"})
        fb = Feedback.objects.get(direction="student_to_teacher")
        self.assertEqual((fb.student, fb.teacher), (self.student, self.teacher))
        self.client.force_login(self.teacher)
        r = self.client.get("/feedback/")
        self.assertContains(r, "Great explanations")
        self.client.post("/feedback/", {"to": self.student.id, "content": "Keep it up"})
        self.client.force_login(self.student)
        self.assertContains(self.client.get("/feedback/"), "Keep it up")

    def test_cannot_write_to_people_outside_your_class(self):
        stranger = Teacher.objects.create_user("stranger", password="Pass-12345")
        self.join()
        self.client.force_login(self.student)
        self.client.post("/feedback/", {"to": stranger.id, "content": "hi"})
        self.assertFalse(Feedback.objects.exists())


class MailTests(Base):   # 12
    def test_send_read_reply_and_email_copy(self):
        self.client.force_login(self.student)
        r = self.client.post("/mail/compose/", {"to": self.teacher.id, "subject": "Question", "body": "Help?"})
        self.assertRedirects(r, "/mail/sent/")
        msg = Message.objects.get()
        self.assertTrue(msg.emailed)
        self.assertEqual(mail.outbox[-1].to, ["t@example.com"])
        self.assertIn("Help?", mail.outbox[-1].body)

        self.client.force_login(self.teacher)
        r = self.client.get("/mail/")
        self.assertContains(r, "Question")
        self.assertContains(r, '<span class="badge">1</span>', html=False)
        self.client.get(f"/mail/{msg.id}/")
        msg.refresh_from_db()
        self.assertTrue(msg.is_read)
        r = self.client.get(f"/mail/compose/?reply={msg.id}")
        self.assertContains(r, "Re: Question")
        self.client.post("/mail/compose/", {"to": self.student.id, "subject": "Re: Question", "body": "Sure",
                                            "parent": msg.id})
        self.assertEqual(Message.objects.get(body="Sure").parent, msg)

    def test_cannot_read_other_peoples_mail(self):
        msg = Message.objects.create(sender=self.teacher, recipient=self.coach, subject="x", body="private")
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(f"/mail/{msg.id}/").status_code, 404)

    def test_api(self):
        api = APIClient()
        api.force_authenticate(self.student)
        r = api.post("/api/messages/", {"recipient": self.teacher.id, "subject": "Hi", "body": "API mail"},
                     format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["sender"], self.student.id)
        api.force_authenticate(self.teacher)
        inbox = api.get("/api/messages/?box=inbox").json()
        self.assertEqual(len(inbox), 1)
        self.assertTrue(api.get(f"/api/messages/{inbox[0]['id']}/").json()["is_read"])
        api.force_authenticate(self.coach)
        self.assertEqual(api.get(f"/api/messages/{inbox[0]['id']}/").status_code, 404)
