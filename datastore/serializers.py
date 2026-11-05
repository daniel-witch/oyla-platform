from django.utils.translation import gettext as _
from rest_framework import serializers

from catalog.models import Step, Resource
from .models import JsonRecord
from .utils import check_data_rules, parse_json_text, FriendlyJSONError


class JsonRecordSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField(read_only=True)
    created_by_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = JsonRecord
        fields = [
            "id", "title", "category", "data", "teacher_comment",
            "created_by", "created_by_id", "created_at", "updated_at",
        ]
        # Students/owners can't write the teacher's comment through the normal
        # endpoint - teachers use POST /api/json-records/<id>/comment/.
        read_only_fields = ["teacher_comment", "created_at", "updated_at"]

    def validate_data(self, value):
        # Allow `data` to be sent as a JSON *string* too - then we can give a
        # friendly "Line X, column Y" message if it's broken.
        if isinstance(value, str):
            try:
                value = parse_json_text(value)
            except FriendlyJSONError as e:
                raise serializers.ValidationError(e.message)
        error = check_data_rules(value)
        if error:
            raise serializers.ValidationError(error)
        return value


class TeacherCommentSerializer(serializers.Serializer):
    teacher_comment = serializers.CharField(allow_blank=True, max_length=5000)


# ---- Course import (nested) ----

class ImportResourceSerializer(serializers.Serializer):
    resource_type = serializers.ChoiceField(choices=Resource.ResourceType.choices)
    body = serializers.CharField(allow_blank=True, required=False, default="")
    link = serializers.URLField(allow_blank=True, required=False, default="")


class ImportStepSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, allow_blank=True, required=False, default="")
    step_type = serializers.ChoiceField(choices=Step.StepType.choices)
    body = serializers.CharField(allow_blank=True, required=False, default="")
    link = serializers.URLField(allow_blank=True, required=False, default="")
    order = serializers.IntegerField(min_value=0, required=False, default=0)
    resource = ImportResourceSerializer(required=False, allow_null=True, default=None)


class ImportLessonSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(allow_blank=True, required=False, default="")
    order = serializers.IntegerField(min_value=0, required=False, default=0)
    steps = ImportStepSerializer(many=True, required=False, default=list)


class ImportModuleSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(allow_blank=True, required=False, default="")
    order = serializers.IntegerField(min_value=0, required=False, default=0)
    lessons = ImportLessonSerializer(many=True, required=False, default=list)


class CourseImportSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    number = serializers.CharField(max_length=50, allow_blank=True, required=False, default="")
    description = serializers.CharField(allow_blank=True, required=False, default="")
    modules = ImportModuleSerializer(many=True, required=False, default=list)


_LEVEL_NAMES = {"modules": "Module", "lessons": "Lesson", "steps": "Step", "resource": "Resource"}


def readable_errors(errors, path=""):
    """Turn DRF's nested error dict into lines like
    'Module 1 → Lesson 2 → Step 3 → step_type: "vidoe" is not a valid choice.'"""
    out = []
    if isinstance(errors, dict):
        for key, val in errors.items():
            items = None
            if key in ("modules", "lessons", "steps"):
                # DRF reports nested-list errors either as a list (one entry per item)
                # or as a dict keyed by the item's index, depending on the version.
                if isinstance(val, dict) and val and all(isinstance(k, int) for k in val):
                    items = sorted(val.items())
                elif isinstance(val, list) and any(isinstance(v, dict) for v in val):
                    items = list(enumerate(val))
            if items is not None:
                for i, item in items:
                    if item:
                        label = f"{_LEVEL_NAMES[key]} {i + 1}"
                        out += readable_errors(item, f"{path} → {label}" if path else label)
            elif key == "resource":
                out += readable_errors(val, f"{path} → Resource" if path else "Resource")
            else:
                prefix = f"{path} → {key}" if path else key
                out += [f"{prefix}: {m}" for m in _flatten_messages(val)]
    elif isinstance(errors, list):
        out += [f"{path}: {m}" if path else str(m) for m in _flatten_messages(errors)]
    return out


def _flatten_messages(val):
    if isinstance(val, (list, tuple)):
        res = []
        for v in val:
            res += _flatten_messages(v)
        return res
    if isinstance(val, dict):
        return [f"{k}: {m}" for k, v in val.items() for m in _flatten_messages(v)]
    return [str(val)]
