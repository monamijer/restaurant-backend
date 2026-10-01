"""Shared pagination: ?page=2&page_size=50, capped to protect the database."""

from rest_framework.pagination import PageNumberPagination

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class StandardPagination(PageNumberPagination):
    page_size = DEFAULT_PAGE_SIZE
    page_size_query_param = "page_size"
    max_page_size = MAX_PAGE_SIZE
