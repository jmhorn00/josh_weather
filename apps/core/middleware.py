"""
Security headers middleware.
Injects Content-Security-Policy and Permissions-Policy headers on every response.
Only active in production (base settings sets CONTENT_SECURITY_POLICY).
"""
from django.conf import settings


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.csp = getattr(settings, 'CONTENT_SECURITY_POLICY', '')
        self.permissions_policy = (
            'geolocation=(self), '
            'camera=(), '
            'microphone=(), '
            'payment=()'
        )

    def __call__(self, request):
        response = self.get_response(request)
        if self.csp:
            response['Content-Security-Policy'] = self.csp
        response['Permissions-Policy'] = self.permissions_policy
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response
