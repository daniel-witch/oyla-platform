import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from catalog.models import Course, Module, Lesson, Step, youtube_id_from_url
from enrollment.models import StepCompletion
from users.models import Student, Teacher

AJAX = {"HTTP_X_REQUESTED_WITH": "fetch", "HTTP_ACCEPT": "application/json"}


class LiveProgressTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(name="Math")
        module = Module.objects.create(course=self.course, name="M1", order=1)
        lesson = Lesson.objects.create(module=module, name="L1", order=1)
        self.video = Step.objects.create(lesson=lesson, step_type="video", body="Watch",
                                         link="https://www.youtube.com/watch?v=5inLLYVQjc0", order=1)
        self.text = Step.objects.create(lesson=lesson, step_type="text", body="Read", order=2)
        self.quiz = Step.objects.create(lesson=lesson, step_type="quiz", body="Q?", order=3)
        self.student = Student.objects.create_user("s", password="pass12345", enrolled_course=self.course)
        self.client.force_login(self.student)

    def test_ajax_complete_returns_json_and_progress(self):
        r = self.client.post(f"/steps/{self.text.id}/", {"action": "complete"}, **AJAX)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["status"], "approved")
        self.assertEqual(data["progress"]["completed_count"], 1)
        self.assertEqual(data["progress"]["total_steps"], 3)
        self.assertEqual(data["progress"]["progress"], 33.3)
        # "complete" again never un-completes (used when a video ends)
        r = self.client.post(f"/steps/{self.text.id}/", {"action": "complete"}, **AJAX)
        self.assertEqual(r.json()["status"], "approved")
        # New rule: a completed step can't be undone.
        r = self.client.post(f"/steps/{self.text.id}/", {"action": "uncomplete"}, **AJAX)
        self.assertEqual(r.json()["status"], "approved")
        self.assertTrue(StepCompletion.objects.filter(step=self.text).exists())

    def test_ajax_quiz_submit_and_empty_answer(self):
        r = self.client.post(f"/steps/{self.quiz.id}/", {"answer": ""}, **AJAX)
        self.assertEqual(r.status_code, 400)
        r = self.client.post(f"/steps/{self.quiz.id}/", {"answer": "B"}, **AJAX)
        self.assertEqual(r.json()["status"], "pending")

    def test_normal_form_post_still_works(self):
        r = self.client.post(f"/steps/{self.text.id}/")
        self.assertRedirects(r, f"/steps/{self.text.id}/")
        self.assertTrue(StepCompletion.objects.filter(step=self.text).exists())

    def test_progress_endpoint(self):
        StepCompletion.objects.create(student=self.student, step=self.video, status="approved")
        StepCompletion.objects.create(student=self.student, step=self.quiz, status="pending", answer="x")
        data = self.client.get("/progress/").json()
        self.assertEqual(data["completed_count"], 1)
        self.assertEqual(data["remaining_count"], 2)
        self.assertEqual(data["steps"], {str(self.video.id): "approved", str(self.quiz.id): "pending"})
        self.client.force_login(Teacher.objects.create_user("t", password="pass12345"))
        self.assertEqual(self.client.get("/progress/").status_code, 403)

    def test_dashboard_and_step_page_render(self):
        r = self.client.get("/", follow=True)   # students land on My Enrollments
        self.assertContains(r, "My Enrollments")
        self.assertContains(r, "Math")
        r = self.client.get(f"/steps/{self.video.id}/")
        self.assertContains(r, "youtube-nocookie.com/embed/5inLLYVQjc0")
        self.assertNotContains(r, "Watch video")


class YoutubeIdTests(TestCase):
    def test_formats(self):
        for url in ["http://www.youtube.com/watch?v=5inLLYVQjc0", "https://youtu.be/5inLLYVQjc0?t=3",
                    "https://www.youtube.com/embed/5inLLYVQjc0", "https://m.youtube.com/watch?v=5inLLYVQjc0&list=x",
                    "https://www.youtube.com/shorts/5inLLYVQjc0"]:
            self.assertEqual(youtube_id_from_url(url), "5inLLYVQjc0", url)
        self.assertEqual(youtube_id_from_url("https://example.com/video.mp4"), "")
        self.assertEqual(youtube_id_from_url(""), "")


class UploadedVideoTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()
        course = Course.objects.create(name="Math")
        other = Course.objects.create(name="Other")
        lesson = Lesson.objects.create(module=Module.objects.create(course=course, name="M"), name="L")
        self.step = Step.objects.create(
            lesson=lesson, step_type="video", body="v",
            video_file=SimpleUploadedFile("lesson.mp4", bytes(range(256)) * 40, content_type="video/mp4"),
        )
        self.student = Student.objects.create_user("s", password="pass12345", enrolled_course=course)
        self.outsider = Student.objects.create_user("o", password="pass12345", enrolled_course=other)

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media, ignore_errors=True)

    def test_full_and_range_requests(self):
        self.client.force_login(self.student)
        r = self.client.get(f"/steps/{self.step.id}/video/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Accept-Ranges"], "bytes")
        self.assertEqual(len(b"".join(r.streaming_content)), 10240)
        r = self.client.get(f"/steps/{self.step.id}/video/", HTTP_RANGE="bytes=100-199")
        self.assertEqual(r.status_code, 206)
        self.assertEqual(r["Content-Range"], "bytes 100-199/10240")
        self.assertEqual(b"".join(r.streaming_content), (bytes(range(256)) * 40)[100:200])
        r = self.client.get(f"/steps/{self.step.id}/video/", HTTP_RANGE="bytes=99999-")
        self.assertEqual(r.status_code, 416)

    def test_step_page_uses_in_app_player(self):
        self.client.force_login(self.student)
        r = self.client.get(f"/steps/{self.step.id}/")
        self.assertContains(r, f'src="/steps/{self.step.id}/video/"')
        self.assertContains(r, "<video")

    def test_access_control(self):
        self.assertEqual(self.client.get(f"/steps/{self.step.id}/video/").status_code, 302)   # not logged in
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(f"/steps/{self.step.id}/video/").status_code, 403)

    def test_bad_extension_rejected(self):
        from django.core.exceptions import ValidationError
        s = Step(lesson=self.step.lesson, step_type="video",
                 video_file=SimpleUploadedFile("virus.exe", b"x"))
        with self.assertRaises(ValidationError):
            s.full_clean()


class WebAppTests(TestCase):
    def test_manifest(self):
        r = self.client.get("/manifest.webmanifest")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/manifest+json")
        data = r.json()
        self.assertEqual(data["display"], "standalone")
        self.assertEqual(data["start_url"], "/?source=app")
        self.assertEqual({i["sizes"] for i in data["icons"]}, {"192x192", "512x512"})

    def test_service_worker(self):
        r = self.client.get("/sw.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("javascript", r["Content-Type"])
        self.assertEqual(r["Service-Worker-Allowed"], "/")
        self.assertIn("/offline/", r.content.decode())

    def test_offline_page_and_head_tags(self):
        self.assertContains(self.client.get("/offline/"), "You're offline")
        r = self.client.get("/login/")
        self.assertContains(r, 'rel="manifest"')
        self.assertContains(r, "serviceWorker")
        self.client.force_login(Student.objects.create_user("x", password="pass12345"))
        self.assertContains(self.client.get("/", follow=True), 'rel="manifest"')


class AdminStepAccessTests(TestCase):
    def test_admin_without_role_can_open_steps(self):
        course = Course.objects.create(name="C")
        lesson = Lesson.objects.create(module=Module.objects.create(course=course, name="M"), name="L")
        video = Step.objects.create(lesson=lesson, step_type="video", body="v",
                                    link="https://youtu.be/5inLLYVQjc0")
        quiz = Step.objects.create(lesson=lesson, step_type="quiz", body="q")
        st = Student.objects.create_user("s", password="pass12345", enrolled_course=course)
        sub = StepCompletion.objects.create(student=st, step=quiz, status="pending", answer="B")
        from users.models import User
        admin = User.objects.create_superuser("boss", "b@example.com", "pass12345")
        self.client.force_login(admin)
        r = self.client.get(f"/steps/{video.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "youtube-nocookie.com/embed/5inLLYVQjc0")
        r = self.client.get(f"/steps/{quiz.id}/")
        self.assertContains(r, "B")
        self.client.post(f"/steps/{quiz.id}/", {"completion_id": sub.id, "action": "approve"})
        self.assertEqual(StepCompletion.objects.get(pk=sub.id).status, "approved")
