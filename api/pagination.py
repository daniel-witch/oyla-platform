from rest_framework.pagination import LimitOffsetPagination


class OylaPagination(LimitOffsetPagination):
    """Pagination for every list endpoint.

    ?limit=10&offset=20  ->  {"count": 57, "next": "...", "previous": "...", "results": [...]}

    Without ?limit the full list is returned as a plain JSON array (as before),
    so existing clients keep working. A page is never larger than 100 items.
    """
    default_limit = None
    max_limit = 100
