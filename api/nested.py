"""Hierarchical (nested) URLs for everything that has a parent.

    /api/courses/{course_pk}/modules/
    /api/courses/{course_pk}/modules/{module_pk}/lessons/
    /api/courses/{course_pk}/modules/{module_pk}/lessons/{lesson_pk}/steps/
    /api/courses/{course_pk}/modules/{module_pk}/lessons/{lesson_pk}/steps/{step_pk}/resources/
    /api/courses/{course_pk}/modules/{module_pk}/lessons/{lesson_pk}/steps/{step_pk}/completions/
    /api/courses/{course_pk}/class-sessions/
    /api/courses/{course_pk}/class-sessions/{class_session_pk}/groups/

Each level has all 5 methods: GET list, POST create, GET one, PUT/PATCH, DELETE.
The parent comes from the URL: on create you don't have to send it, and a child
can only be reached through its real parents (course 1 / module of course 2 -> 404).
The flat URLs (/api/modules/ etc.) keep working too.
"""
from django.urls import path
from rest_framework.exceptions import NotFound

from catalog.models import Course, Module, Lesson, Step
from enrollment.models import ClassSession
from . import views


class NestedMixin:
    # url kwarg -> queryset lookup used to filter the children
    parent_filters = {}
    # (body field, url kwarg) the parent is set from on create / update
    parent_field = None
    # list of (model, {model lookup: url kwarg}) that must exist, checked top-down
    parent_checks = []

    def check_parents(self):
        for model, lookups in self.parent_checks:
            if not model.objects.filter(**{k: self.kwargs[v] for k, v in lookups.items()}).exists():
                raise NotFound(f"No {model.__name__} matches the given query.")

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.check_parents()

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(**{lookup: self.kwargs[kw] for kw, lookup in self.parent_filters.items()})

    def _with_parent(self, request):
        data = request.data
        if hasattr(data, "copy") and not isinstance(data, (list, str)):
            data = data.copy()
            field, kw = self.parent_field
            data[field] = int(self.kwargs[kw])
            request._full_data = data
        return request

    def create(self, request, *args, **kwargs):
        return super().create(self._with_parent(request), *args, **kwargs)

    def update(self, request, *args, **kwargs):
        return super().update(self._with_parent(request), *args, **kwargs)


C = {"pk": "course_pk"}
M = {"pk": "module_pk", "course_id": "course_pk"}
L = {"pk": "lesson_pk", "module_id": "module_pk", "module__course_id": "course_pk"}
S = {"pk": "step_pk", "lesson_id": "lesson_pk", "lesson__module_id": "module_pk", "lesson__module__course_id": "course_pk"}


class CourseModules(NestedMixin, views.ModuleViewSet):
    parent_filters = {"course_pk": "course_id"}
    parent_field = ("course", "course_pk")
    parent_checks = [(Course, C)]


class ModuleLessons(NestedMixin, views.LessonViewSet):
    parent_filters = {"module_pk": "module_id", "course_pk": "module__course_id"}
    parent_field = ("module", "module_pk")
    parent_checks = [(Course, C), (Module, M)]


class LessonSteps(NestedMixin, views.StepViewSet):
    parent_filters = {"lesson_pk": "lesson_id", "module_pk": "lesson__module_id", "course_pk": "lesson__module__course_id"}
    parent_field = ("lesson", "lesson_pk")
    parent_checks = [(Course, C), (Module, M), (Lesson, L)]


class StepResources(NestedMixin, views.ResourceViewSet):
    parent_filters = {"step_pk": "step_id", "lesson_pk": "step__lesson_id"}
    parent_field = ("step", "step_pk")
    parent_checks = [(Course, C), (Module, M), (Lesson, L), (Step, S)]


class StepCompletions(NestedMixin, views.StepCompletionViewSet):
    parent_filters = {"step_pk": "step_id", "lesson_pk": "step__lesson_id"}
    parent_field = ("step", "step_pk")
    parent_checks = [(Course, C), (Module, M), (Lesson, L), (Step, S)]


class CourseClassSessions(NestedMixin, views.ClassSessionViewSet):
    parent_filters = {"course_pk": "course_id"}
    parent_field = ("course", "course_pk")
    parent_checks = [(Course, C)]


class ClassSessionGroups(NestedMixin, views.GroupViewSet):
    parent_filters = {"class_session_pk": "class_session_id", "course_pk": "class_session__course_id"}
    parent_field = ("class_session", "class_session_pk")
    parent_checks = [(Course, C), (ClassSession, {"pk": "class_session_pk", "course_id": "course_pk"})]


LIST = {"get": "list", "post": "create"}
DETAIL = {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}


def routes(prefix, viewset, name):
    return [
        path(prefix, viewset.as_view(LIST), name=f"{name}-list"),
        path(prefix + "<int:pk>/", viewset.as_view(DETAIL), name=f"{name}-detail"),
    ]


c = "courses/<int:course_pk>/"
m = c + "modules/<int:module_pk>/"
le = m + "lessons/<int:lesson_pk>/"
st = le + "steps/<int:step_pk>/"

urlpatterns = (
    routes(c + "modules/", CourseModules, "course-modules")
    + routes(m + "lessons/", ModuleLessons, "module-lessons")
    + routes(le + "steps/", LessonSteps, "lesson-steps")
    + routes(st + "resources/", StepResources, "step-resources")
    + routes(st + "completions/", StepCompletions, "step-completions-nested")
    + routes(c + "class-sessions/", CourseClassSessions, "course-class-sessions")
    + routes(c + "class-sessions/<int:class_session_pk>/groups/", ClassSessionGroups, "class-session-groups")
)
