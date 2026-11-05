from django.urls import path

from . import views

urlpatterns = [
    path("", views.record_list, name="data_list"),
    path("new/", views.record_create, name="data_new"),
    path("import-course/", views.course_import, name="data_import_course"),
    path("<int:pk>/", views.record_detail, name="data_detail"),
    path("<int:pk>/edit/", views.record_edit, name="data_edit"),
    path("<int:pk>/delete/", views.record_delete, name="data_delete"),
    path("<int:pk>/download/", views.record_download, name="data_download"),
]
