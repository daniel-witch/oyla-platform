"""Filtering for every list endpoint, without extra packages.

Each ViewSet can declare:

    filterset_fields = {"course": "course", "student": "student"}   # ?course=3
    search_fields    = ["name", "description"]                      # ?search=logic
    ordering_fields  = ["id", "name"]                                # ?ordering=-name

FieldFilterBackend handles `filterset_fields`; DRF's own SearchFilter and
OrderingFilter (switched on in settings.py) handle `search` and `ordering`.
A value of the wrong type (e.g. ?course=abc) gives 400 with the reason,
never a server error.
"""
from django.core.exceptions import FieldError, ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError
from rest_framework.filters import BaseFilterBackend

TRUE = {"true", "1", "yes"}
FALSE = {"false", "0", "no"}


class FieldFilterBackend(BaseFilterBackend):
    def get_fields(self, view):
        fields = getattr(view, "filterset_fields", None) or {}
        if isinstance(fields, (list, tuple)):
            fields = {f: f for f in fields}
        return fields

    def filter_queryset(self, request, queryset, view):
        for param, lookup in self.get_fields(view).items():
            if param not in request.query_params:
                continue
            value = request.query_params.get(param)
            low = value.strip().lower()
            if low in ("null", "none"):
                kwargs = {f"{lookup}__isnull": True}
            elif low in TRUE | FALSE and (lookup.endswith("__isnull") or self._is_bool(queryset, lookup)):
                kwargs = {lookup: low in TRUE}
            else:
                kwargs = {lookup: value}
            try:
                queryset = queryset.filter(**kwargs)
                queryset.exists()  # make the database check the value now
            except (ValueError, TypeError, DjangoValidationError, FieldError, OverflowError):
                raise ValidationError({param: [f"'{value}' is not a valid value for this filter."]})
        return queryset

    @staticmethod
    def _is_bool(queryset, lookup):
        try:
            model = queryset.model
            parts = lookup.split("__")
            for p in parts[:-1]:
                model = model._meta.get_field(p).related_model
            return model._meta.get_field(parts[-1]).get_internal_type() == "BooleanField"
        except Exception:
            return False

    # Shown in the browsable API / schema
    def get_schema_operation_parameters(self, view):
        return [{"name": p, "required": False, "in": "query", "schema": {"type": "string"}}
                for p in self.get_fields(view)]
