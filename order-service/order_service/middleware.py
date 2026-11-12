class JWTFromCookieMiddleware:
    """Bridge HttpOnly JWT cookies to DRF's standard Authorization header."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if 'HTTP_AUTHORIZATION' not in request.META:
            access_token = request.COOKIES.get('access_token')
            if access_token:
                request.META['HTTP_AUTHORIZATION'] = f'Bearer {access_token}'
        return self.get_response(request)
