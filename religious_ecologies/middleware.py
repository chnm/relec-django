from django.db import connection
from django.http import JsonResponse


class HealthCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/health/":
            try:
                connection.ensure_connection()
                return JsonResponse({"status": "ok", "code": 200})
            except Exception:
                return JsonResponse(
                    {"status": "error", "code": 503, "detail": "database unavailable"},
                    status=503,
                )
        return self.get_response(request)
