from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import IsTeacherOrCoach, IsOwnerOrStaffRole
from catalog.models import Course
from .importer import import_course, export_course, CourseImportError
from .serializers import JsonRecordSerializer, TeacherCommentSerializer
from .utils import (
    visible_records, filter_records, over_record_limit, limit_message, pretty,
    parse_json_text, FriendlyJSONError,
)


def json_download_response(record):
    response = HttpResponse(pretty(record.data), content_type="application/json; charset=utf-8")
    filename = (slugify(record.title) or f"record-{record.pk}") + ".json"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class JsonRecordViewSet(viewsets.ModelViewSet):
    """/api/json-records/ - save any JSON.

    Students see only their own records; teachers/coaches also see their students'.
    Filters: ?category=quiz  ?search=text
    """
    serializer_class = JsonRecordSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrStaffRole]
    filterset_fields = {"category": "category", "created_by": "created_by"}
    search_fields = ["title", "teacher_comment"]
    ordering_fields = ["id", "created_at", "updated_at", "title"]

    def get_queryset(self):
        qs = visible_records(self.request.user)
        return filter_records(
            qs,
            search=self.request.query_params.get("search", "").strip(),
            category=self.request.query_params.get("category", "").strip(),
        )

    def create(self, request, *args, **kwargs):
        if over_record_limit(request.user):
            return Response({"detail": limit_message()}, status=status.HTTP_400_BAD_REQUEST)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        return json_download_response(self.get_object())

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated, IsTeacherOrCoach],
            serializer_class=TeacherCommentSerializer)
    def comment(self, request, pk=None):
        record = self.get_object()
        ser = TeacherCommentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        record.teacher_comment = ser.validated_data["teacher_comment"]
        record.save(update_fields=["teacher_comment", "updated_at"])
        return Response(JsonRecordSerializer(record).data)


class CourseImportView(APIView):
    """POST /api/import/course/  (teachers, coaches, superusers only)

    Body: the course JSON. Add "update_existing": true (in the body or as
    ?update_existing=true) to replace the course that has the same "number".
    """
    permission_classes = [permissions.IsAuthenticated, IsTeacherOrCoach]

    def post(self, request):
        raw = request.data
        if isinstance(raw, str):
            try:
                raw = parse_json_text(raw)
            except FriendlyJSONError as e:
                return Response({"errors": [e.message]}, status=status.HTTP_400_BAD_REQUEST)
        if hasattr(raw, "dict") and not isinstance(raw, dict):   # QueryDict from a form post
            raw = raw.dict()
        update_existing = request.query_params.get("update_existing", "").lower() in ("1", "true", "yes")
        try:
            result = import_course(raw, update_existing=update_existing, user=request.user)
        except CourseImportError as e:
            return Response({"errors": e.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_201_CREATED if result["created"] else status.HTTP_200_OK)


class CourseExportView(APIView):
    """GET /api/courses/<id>/export/ - the same JSON the importer accepts."""

    def get(self, request, pk):
        course = get_object_or_404(Course, pk=pk)
        return Response(export_course(course))
