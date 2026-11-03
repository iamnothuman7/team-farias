from django.utils.cache import add_never_cache_headers


class PrivateResponseMiddleware:
    """HTML pode conter sessão, CSRF ou dados pessoais, inclusive no site público."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if "text/html" in response.get("Content-Type", ""):
            add_never_cache_headers(response)
            if request.headers.get("HX-Boosted") == "true" and response.status_code == 200:
                response["HX-Push-Url"] = request.get_full_path()
        return response
