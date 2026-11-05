"""Stream uploaded step videos from this server, with seeking support.

Browsers (especially Safari/iPhone) need HTTP "Range" requests to play and
seek in a video, which Django's default file serving doesn't support - so
this view handles it. It also checks the viewer is allowed to see the step.
"""
import mimetypes
import os
import re

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404

from catalog.models import Step

CHUNK = 64 * 1024
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def can_view_step(user, step):
    if user.is_superuser or user.is_staff:
        return True
    role = getattr(user, "role", "")
    if role in ("teacher", "coach"):
        return True
    if role == "student":
        return user.student.enrolled_course_id == step.lesson.module.course_id
    return False


def _file_iterator(f, length):
    try:
        remaining = length
        while remaining > 0:
            data = f.read(min(CHUNK, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data
    finally:
        f.close()


@login_required
def step_video(request, step_id):
    step = get_object_or_404(Step.objects.select_related("lesson__module"), pk=step_id)
    if not step.video_file:
        raise Http404("This step has no uploaded video.")
    if not can_view_step(request.user, step):
        raise PermissionDenied
    try:
        path = step.video_file.path
        size = os.path.getsize(path)
    except (OSError, ValueError, NotImplementedError):
        raise Http404("Video file is missing on the server.")
    content_type = mimetypes.guess_type(path)[0] or "video/mp4"

    match = RANGE_RE.match(request.META.get("HTTP_RANGE", "").strip())
    if match and (match.group(1) or match.group(2)):
        first, last = match.group(1), match.group(2)
        if first == "":                       # "bytes=-500" = last 500 bytes
            start, end = max(size - int(last), 0), size - 1
        else:
            start = int(first)
            end = min(int(last), size - 1) if last else size - 1
        if start >= size or start > end:
            resp = HttpResponse(status=416)
            resp["Content-Range"] = f"bytes */{size}"
            return resp
        length = end - start + 1
        f = open(path, "rb")
        f.seek(start)
        resp = StreamingHttpResponse(_file_iterator(f, length), status=206, content_type=content_type)
        resp["Content-Range"] = f"bytes {start}-{end}/{size}"
        resp["Content-Length"] = str(length)
    else:
        resp = FileResponse(open(path, "rb"), content_type=content_type)
        resp["Content-Length"] = str(size)

    resp["Accept-Ranges"] = "bytes"
    resp["Content-Disposition"] = "inline"
    resp["Cache-Control"] = "private, max-age=3600"
    return resp
