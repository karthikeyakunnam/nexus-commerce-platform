"""HttpOnly JWT cookie helpers used by authentication endpoints."""

from django.conf import settings
from django.middleware.csrf import get_token


ACCESS_COOKIE = 'access_token'
REFRESH_COOKIE = 'refresh_token'


def set_auth_cookies(response, access_token, refresh_token=None, request=None):
    secure = not settings.DEBUG
    same_site = 'Lax'
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=15 * 60,
        secure=secure,
        httponly=True,
        samesite=same_site,
        path='/',
    )
    if refresh_token:
        response.set_cookie(
            REFRESH_COOKIE,
            refresh_token,
            max_age=24 * 60 * 60,
            secure=secure,
            httponly=True,
            samesite=same_site,
            path='/',
        )
    if request is not None:
        response.set_cookie(
            'csrftoken',
            get_token(request),
            max_age=24 * 60 * 60,
            secure=secure,
            httponly=False,
            samesite=same_site,
            path='/',
        )
    return response


def clear_auth_cookies(response):
    response.delete_cookie(ACCESS_COOKIE, path='/')
    response.delete_cookie(REFRESH_COOKIE, path='/')
    response.delete_cookie('csrftoken', path='/')
    return response
