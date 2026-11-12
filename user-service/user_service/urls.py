"""
URL configuration for UserService.

Educational Note: This service exposes:
1. REST API endpoints for user management
2. JWT token endpoints (obtain, refresh)
3. Public key endpoint for other services
4. Swagger/OpenAPI documentation
"""

from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from users import views
from users.serializers import CustomTokenObtainPairSerializer
from users.auth_cookies import set_auth_cookies, clear_auth_cookies


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom token view that returns user data along with tokens.
    
    Educational Note: This allows the frontend to get user information
    during login without making an additional API call.
    """
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            access = response.data.pop('access', None)
            refresh = response.data.pop('refresh', None)
            if access and refresh:
                set_auth_cookies(response, access, refresh, request=request)
        return response


class CookieTokenRefreshView(TokenRefreshView):
    """Refresh using the HttpOnly refresh cookie; never expose tokens to JS."""

    serializer_class = TokenRefreshSerializer

    def post(self, request, *args, **kwargs):
        data = request.data.copy()
        data['refresh'] = data.get('refresh') or request.COOKIES.get('refresh_token')
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        response = Response(serializer.validated_data, status=status.HTTP_200_OK)
        access = response.data.pop('access', None)
        refresh = response.data.pop('refresh', None)
        if access:
            set_auth_cookies(response, access, refresh, request=request)
        return response


class LogoutView(views.APIView):
    permission_classes = []

    def post(self, request):
        response = Response({'message': 'Logged out'}, status=status.HTTP_200_OK)
        return clear_auth_cookies(response)


urlpatterns = [
    # Admin interface
    path('admin/', admin.site.urls),
    
    # Health check endpoint (at root for Docker healthcheck)
    path('health/', views.health_check, name='health'),
    
    # API endpoints (includes users app URLs)
    # This will make /api/users/, /api/users/2fa/, etc. available
    path('api/', include('users.urls')),
    
    # JWT token endpoints
    # Educational Note: These endpoints use RS256 (RSA) for signing tokens
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', CookieTokenRefreshView.as_view(), name='token_refresh'),
    path('api/logout/', LogoutView.as_view(), name='logout'),
    
    # API documentation (Swagger UI)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
