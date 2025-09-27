from rest_framework.pagination import PageNumberPagination

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20                      # default items per page
    page_size_query_param = 'page_size' # allow client to set ?page_size=50
    max_page_size = 100                 # don’t allow more than 100 per request
