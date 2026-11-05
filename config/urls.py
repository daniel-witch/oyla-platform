"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.urls import path, include, re_path
from django.views.static import serve as serve_media
from portal import views as portal_views
from portal import video as portal_video
from portal import pwa as portal_pwa
from portal import views_learning, views_people
from communication import views as comm_views

urlpatterns = [
    path('manifest.webmanifest', portal_pwa.manifest, name='pwa_manifest'),
    path('sw.js', portal_pwa.service_worker, name='pwa_service_worker'),
    path('offline/', portal_pwa.offline, name='pwa_offline'),
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('data/', include('datastore.urls')),
    path('login/', auth_views.LoginView.as_view(template_name='portal/login.html'), name='login'),
    path('signup/', portal_views.signup, name='signup'),
    path('signup/verify/', portal_views.signup_verify, name='signup_verify'),
    path('password-change/', auth_views.PasswordChangeView.as_view(
        template_name='portal/password_change_form.html', success_url='/password-change/done/'
    ), name='password_change'),
    path('password-change/done/', auth_views.PasswordChangeDoneView.as_view(
        template_name='portal/password_change_done.html'
    ), name='password_change_done'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),
    path('steps/<int:step_id>/', portal_views.step_detail, name='step_detail'),
    path('steps/<int:step_id>/video/', portal_video.step_video, name='step_video'),
    path('progress/', portal_views.student_progress, name='student_progress'),
    path('students/<int:student_id>/feedback/', portal_views.give_feedback, name='give_feedback'),
    path('meetups/<int:meetup_id>/respond/', portal_views.respond_meetup, name='respond_meetup'),
    path('meetups/request/', portal_views.request_meetup, name='request_meetup'),
    path('', portal_views.dashboard, name='dashboard'),

    # My Enrollments: courses -> modules -> lessons (students)
    path('enrollments/', views_learning.enrollments, name='enrollments'),
    path('enrollments/course/<int:course_id>/', views_learning.course_detail, name='course_detail'),
    path('enrollments/module/<int:module_id>/', views_learning.module_detail, name='module_detail'),
    # Study module (course programme) - in everyone's menu
    path('study-module/', views_learning.study_module, name='study_module'),
    path('study-module/<int:course_id>/', views_learning.study_module_course, name='study_module_course'),
    # Profile, feedback, invite links
    path('profile/', views_people.profile, name='profile'),
    path('feedback/', views_people.feedback, name='feedback'),
    path('invites/', views_people.invites, name='invites'),
    path('join/', views_people.join_by_code, name='join_by_code'),
    path('join/<str:token>/', views_people.join_class, name='join_class'),
    # Announcements (newspaper) and Mail
    path('announcements/', comm_views.announcements, name='announcements'),
    path('announcements/new/', comm_views.announcement_new, name='announcement_new'),
    path('announcements/<int:pk>/', comm_views.announcement_detail, name='announcement_detail'),
    path('mail/', comm_views.mail_inbox, name='mail_inbox'),
    path('mail/sent/', comm_views.mail_sent, name='mail_sent'),
    path('mail/compose/', comm_views.mail_compose, name='mail_compose'),
    path('mail/<int:pk>/', comm_views.mail_detail, name='mail_detail'),

    # Uploaded files (profile photos). Served by Django itself so photos also work
    # on the Render deployment (fine for a course project's traffic).
    re_path(r'^media/(?P<path>avatars/.*)$', lambda request, path: serve_media(request, path, settings.MEDIA_ROOT)),
]
