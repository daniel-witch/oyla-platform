import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.translation import gettext as _

from .api_views import json_download_response
from .forms import JsonRecordForm, CourseImportForm, TeacherCommentForm
from .importer import import_course, CourseImportError
from .models import JsonRecord
from .utils import (
    visible_records, filter_records, over_record_limit, limit_message,
    is_teacher_or_coach, role_of, pretty,
)

EXAMPLE_JSON = {
    "name": "Aruzhan",
    "grade": 10,
    "answers": ["B", "D", "A"],
    "finished": True,
}

COURSE_EXAMPLE = {
    "name": "Critical Thinking Math",
    "number": "CT-101",
    "description": "Sample course",
    "modules": [{
        "name": "Ratios & Proportional Relationships", "description": "", "order": 1,
        "lessons": [{
            "name": "Lesson 1.1", "description": "", "order": 1,
            "steps": [
                {"step_type": "video", "body": "Watch the intro video.",
                 "link": "https://www.youtube.com/watch?v=example", "order": 1,
                 "resource": {"resource_type": "video", "body": "", "link": "https://www.youtube.com/watch?v=example"}},
                {"step_type": "quiz", "body": "1) 2:3 = 4:? A) 5 B) 6 C) 8 D) 9", "order": 2},
            ],
        }],
    }],
}


def _ctx(request, **extra):
    user = request.user
    extra.setdefault("nav_active", "data")
    return {"user": user, "role": role_of(user), "is_staff_role": is_teacher_or_coach(user), **extra}


@login_required
def record_list(request):
    search = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    base = visible_records(request.user)
    records = filter_records(base, search=search, category=category)
    categories = (base.exclude(category="").order_by("category")
                  .values_list("category", flat=True).distinct())
    return render(request, "datastore/list.html", _ctx(
        request, records=records[:300], search=search, category=category, categories=categories,
        total=records.count(),
    ))


@login_required
def record_create(request):
    if request.method == "POST":
        if over_record_limit(request.user):
            messages.error(request, limit_message())
            return redirect("data_list")
        form = JsonRecordForm(request.POST, request.FILES)
        if form.is_valid():
            record = JsonRecord.objects.create(
                title=form.cleaned_data["title"],
                category=form.cleaned_data["category"].strip(),
                data=form.cleaned_data["data"],
                created_by=request.user,
            )
            messages.success(request, _("Saved! Your data is now stored in the database."))
            return redirect("data_detail", pk=record.pk)
    else:
        form = JsonRecordForm()
    return render(request, "datastore/form.html", _ctx(
        request, form=form, mode="new", example=pretty(EXAMPLE_JSON),
    ))


def _get_visible(request, pk):
    return get_object_or_404(visible_records(request.user), pk=pk)


def _is_owner(request, record):
    return request.user.is_superuser or record.created_by_id == request.user.pk


@login_required
def record_detail(request, pk):
    record = _get_visible(request, pk)
    comment_form = None
    if is_teacher_or_coach(request.user):
        if request.method == "POST":
            comment_form = TeacherCommentForm(request.POST)
            if comment_form.is_valid():
                record.teacher_comment = comment_form.cleaned_data["teacher_comment"]
                record.save(update_fields=["teacher_comment", "updated_at"])
                messages.success(request, _("Comment saved."))
                return redirect("data_detail", pk=record.pk)
        else:
            comment_form = TeacherCommentForm(initial={"teacher_comment": record.teacher_comment})
    elif request.method == "POST":
        raise PermissionDenied
    return render(request, "datastore/detail.html", _ctx(
        request, record=record, pretty_json=pretty(record.data),
        can_edit=_is_owner(request, record), comment_form=comment_form,
    ))


@login_required
def record_edit(request, pk):
    record = _get_visible(request, pk)
    if not _is_owner(request, record):
        raise PermissionDenied
    if request.method == "POST":
        form = JsonRecordForm(request.POST, request.FILES)
        if form.is_valid():
            record.title = form.cleaned_data["title"]
            record.category = form.cleaned_data["category"].strip()
            record.data = form.cleaned_data["data"]
            record.save()
            messages.success(request, _("Changes saved."))
            return redirect("data_detail", pk=record.pk)
    else:
        form = JsonRecordForm(initial={
            "title": record.title, "category": record.category, "json_text": pretty(record.data),
        })
    return render(request, "datastore/form.html", _ctx(
        request, form=form, mode="edit", record=record, example=pretty(EXAMPLE_JSON),
    ))


@login_required
def record_delete(request, pk):
    record = _get_visible(request, pk)
    if not _is_owner(request, record):
        raise PermissionDenied
    if request.method == "POST":
        record.delete()
        messages.success(request, _("Deleted."))
        return redirect("data_list")
    return render(request, "datastore/confirm_delete.html", _ctx(request, record=record))


@login_required
def record_download(request, pk):
    return json_download_response(_get_visible(request, pk))


@login_required
def course_import(request):
    if not is_teacher_or_coach(request.user):
        raise PermissionDenied
    result = None
    import_errors = []
    if request.method == "POST":
        form = CourseImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                result = import_course(
                    form.cleaned_data["data"],
                    update_existing=form.cleaned_data["update_existing"],
                    user=request.user,
                )
                messages.success(request, _("Course imported successfully."))
            except CourseImportError as e:
                import_errors = e.messages
    else:
        form = CourseImportForm()
    return render(request, "datastore/import_course.html", _ctx(
        request, form=form, result=result, import_errors=import_errors, nav_active="import",
        example=json.dumps(COURSE_EXAMPLE, ensure_ascii=False, indent=2),
    ))
