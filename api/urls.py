from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views, nested
from datastore import api_views as datastore_views

router = DefaultRouter()
router.register("users", views.UserViewSet, basename="user")
router.register("students", views.StudentViewSet, basename="student")
router.register("teachers", views.TeacherViewSet, basename="teacher")
router.register("coaches", views.CoachViewSet, basename="coach")
router.register("courses", views.CourseViewSet, basename="course")
router.register("modules", views.ModuleViewSet, basename="module")
router.register("lessons", views.LessonViewSet, basename="lesson")
router.register("steps", views.StepViewSet, basename="step")
router.register("resources", views.ResourceViewSet, basename="resource")
router.register("class-sessions", views.ClassSessionViewSet, basename="classsession")
router.register("groups", views.GroupViewSet, basename="group")
router.register("step-completions", views.StepCompletionViewSet, basename="stepcompletion")
router.register("feedbacks", views.FeedbackViewSet, basename="feedback")
router.register("meetups", views.MeetupViewSet, basename="meetup")
router.register("invites", views.ClassInviteViewSet, basename="classinvite")
router.register("announcements", views.AnnouncementViewSet, basename="announcement")
router.register("messages", views.MessageViewSet, basename="message")
router.register("json-records", datastore_views.JsonRecordViewSet, basename="jsonrecord")

urlpatterns = [
    path("auth/signup/", views.SignupView.as_view(), name="api-signup"),
    path("auth/signup/verify/", views.SignupVerifyView.as_view(), name="api-signup-verify"),
    path("auth/login/", views.LoginView.as_view(), name="api-login"),
    path("auth/logout/", views.LogoutView.as_view(), name="api-logout"),
    path("auth/password-change/", views.PasswordChangeView.as_view(), name="api-password-change"),
    path("auth/me/", views.MeView.as_view(), name="api-me"),
    path("invites/join/", views.JoinClassView.as_view(), name="api-join-class"),
    path("my/enrollments/", views.MyEnrollmentsView.as_view(), name="api-my-enrollments"),
    path("dashboard/", views.DashboardView.as_view(), name="api-dashboard"),
    path("import/course/", datastore_views.CourseImportView.as_view(), name="api-import-course"),
    path("courses/<int:pk>/export/", datastore_views.CourseExportView.as_view(), name="api-course-export"),
    # hierarchical URLs: /api/courses/1/modules/2/lessons/3/steps/4/ ...
    path("", include(nested.urlpatterns)),
    path("", include(router.urls)),
]
