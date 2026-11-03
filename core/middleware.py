from django.utils.cache import add_never_cache_headers


class PrivateResponseMiddleware:
    """HTML pode conter sessão, CSRF ou dados pessoais, inclusive no site público."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if "text/html" in response.get("Content-Type", ""):
            add_never_cache_headers(response)
            # Scripts somente do próprio site; mantém estilos dinâmicos da marca.
            policy = (
                "default-src 'self'; script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; "
                "font-src 'self'; connect-src 'self'; worker-src 'self'; "
                "manifest-src 'self'; object-src 'none'; base-uri 'none'; "
                "frame-ancestors 'none'; form-action 'self'"
            )
            if request.is_secure():
                policy += "; upgrade-insecure-requests"
            response["Content-Security-Policy"] = policy
            response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
            if request.headers.get("HX-Boosted") == "true" and response.status_code == 200:
                response["HX-Push-Url"] = request.get_full_path()
        return response
