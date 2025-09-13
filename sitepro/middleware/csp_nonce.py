# sitepro/middleware/csp_nonce.py
import secrets


class CSPNonceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        nonce = secrets.token_urlsafe(16)
        request.csp_nonce = nonce

        resp = self.get_response(request)

        # Politique compacte avec nonce appliqué
        policy = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}'; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'self'; "
            "base-uri 'self'"
        )
        resp["Content-Security-Policy"] = policy
        return resp
