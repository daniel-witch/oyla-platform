"""Turns 'bad number' crashes into a clean error instead of a 500.

Someone can send an ID like 99999999999999999999 in a URL or a field. Python
handles it, but the database can't store it and raises OverflowError (SQLite)
or DataError (Postgres). Without this, Django answers 500 Internal Server Error.
"""
import re

from django.db import DataError
from django.http import Http404, JsonResponse

BIG_NUMBER_IN_PATH = re.compile(r"/-?\d{19,}(/|$)")


class BadNumberMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        # Letters where the database expects a number, e.g. ?reply=abc or to=abc in a form.
        if isinstance(exception, ValueError) and "expected a number" in str(exception):
            if request.path.startswith("/api/"):
                return JsonResponse({"detail": "Expected a number."}, status=400)
            raise Http404("Not found.")
        if not isinstance(exception, (OverflowError, DataError)):
            return None
        in_url = bool(BIG_NUMBER_IN_PATH.search(request.path))
        if request.path.startswith("/api/"):
            if in_url:
                return JsonResponse({"detail": "Not found."}, status=404)
            return JsonResponse({"detail": "A value in your request is too large or invalid for the database."},
                                status=400)
        raise Http404("Not found.")


class ApiSafetyNetMiddleware:
    """Last line of defence for the API: if anything unexpected still goes wrong,
    answer with a short JSON error instead of a long HTML debug page, and log it."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if not request.path.startswith("/api/") or isinstance(exception, Http404):
            return None
        import logging
        logging.getLogger("django.request").exception("Unhandled API error on %s %s", request.method, request.path)
        return JsonResponse({"detail": "Something went wrong on the server. The error was logged."}, status=500)


class ApiUrlMiddleware:
    """Keeps every /api/ answer JSON, even for badly typed URLs.

    1. A URL without the final slash (/api/courses or /api/courses/5) is treated
       as if it had one. Without this, Django crashes on POST/PUT/PATCH/DELETE
       ("can't redirect a POST to the slash version") and answers 500.
    2. If an /api/ answer would still be an HTML error page (404 for an unknown
       address, or a 500), it is replaced by a short JSON error.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        is_api = request.path_info.startswith("/api/") or request.path_info == "/api"
        if is_api and not request.path_info.endswith("/"):
            request.path_info += "/"
            request.path += "/"
        response = self.get_response(request)
        if is_api and "text/html" in response.get("Content-Type", ""):
            if response.status_code == 404:
                return JsonResponse({"detail": "Not found. Check the address, e.g. /api/courses/5/"}, status=404)
            if response.status_code >= 500:
                return JsonResponse({"detail": "Something went wrong on the server. The error was logged."},
                                    status=response.status_code)
        return response
