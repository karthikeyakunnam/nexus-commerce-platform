"""
Django settings for ProductService.

Educational Note: This service VERIFIES JWT tokens (doesn't sign them).
It fetches the public key from UserService and uses it to verify tokens locally.

Key Difference from UserService:
- UserService: Has PRIVATE key (signs tokens)
- ProductService: Has PUBLIC key only (verifies tokens)
- No need to call UserService for every request! (50% latency reduction)
"""

import os
import requests
from pathlib import Path
from datetime import timedelta
from urllib.parse import urlparse
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
DEBUG = os.getenv('DEBUG', 'True').lower() in {'1', 'true', 'yes', 'on'}
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'dev-only-secret-key-change-in-production'
    else:
        raise ImproperlyConfigured('SECRET_KEY must be set when DEBUG=False')

_allowed_hosts = os.getenv('ALLOWED_HOSTS') or ('*' if DEBUG else '')
ALLOWED_HOSTS = [host.strip() for host in _allowed_hosts.split(',') if host.strip()]
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured('ALLOWED_HOSTS must contain at least one host')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'drf_spectacular',
    'corsheaders',
    
    # Local apps
    'products',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'product_service.request_id.RequestIDMiddleware',
    'product_service.middleware.JWTFromCookieMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'product_service.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'product_service.wsgi.application'

# Database
# Educational Note: Each service has its own database (service isolation)
def database_config():
    database_url = os.getenv('DATABASE_URL', 'sqlite:///data/db.sqlite3')
    parsed = urlparse(database_url)
    if parsed.scheme.startswith('postgres'):
        return {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': parsed.path.lstrip('/'),
            'USER': parsed.username or '',
            'PASSWORD': parsed.password or '',
            'HOST': parsed.hostname or 'localhost',
            'PORT': str(parsed.port or 5432),
            'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '60')),
        }
    if parsed.scheme == 'sqlite':
        sqlite_path = parsed.path
        if sqlite_path == '/data/db.sqlite3':
            sqlite_path = str(BASE_DIR / 'data' / 'db.sqlite3')
        return {'ENGINE': 'django.db.backends.sqlite3', 'NAME': sqlite_path}
    raise ImproperlyConfigured(f'Unsupported DATABASE_URL scheme: {parsed.scheme}')


DATABASES = {'default': database_config()}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ============================================================================
# Redis Cache Configuration
# Educational Note: Redis provides fast in-memory caching for:
# - Product catalog caching (reduce database queries)
# - API response caching
# - Rate limiting
# - Session management
# ============================================================================

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.getenv('REDIS_URL', 'redis://redis:6379/2'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'product_service',
        'TIMEOUT': 300,  # Default timeout: 5 minutes
    }
}

# CORS settings
_cors_origins = [origin.strip() for origin in os.getenv('CORS_ALLOWED_ORIGINS', '').split(',') if origin.strip()]
CORS_ALLOW_ALL_ORIGINS = DEBUG and not _cors_origins
CORS_ALLOWED_ORIGINS = _cors_origins
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.getenv('CSRF_TRUSTED_ORIGINS', ','.join(_cors_origins)).split(',') if origin.strip()]

# ============================================================================
# Fetch Public Key from UserService
# Educational Note: This is the KEY to our RSA JWT architecture!
# ============================================================================

def fetch_public_key_from_user_service():
    """
    Fetch RSA public key from UserService for JWT verification.
    
    Educational Note: This is called once on startup.
    ProductService can then verify JWT tokens LOCALLY without calling UserService!
    
    Benefits:
    - 50% latency reduction (no network call per request)
    - UserService load reduced by 80%+
    - Services work even if UserService is down
    - Industry standard (OAuth2/OpenID Connect pattern)
    
    Strategy:
    1. Try to read from shared volume (fastest)
    2. Fetch from UserService HTTP endpoint with retry (fallback)
    3. Return None if all attempts fail (degraded mode)
    """
    if os.getenv('SKIP_PUBLIC_KEY_FETCH', 'false').lower() in {'1', 'true', 'yes', 'on'}:
        return None

    import time
    
    user_service_url = os.getenv('USER_SERVICE_URL', 'http://user-service:8000')
    public_key_path = os.getenv('JWT_PUBLIC_KEY_PATH', str(BASE_DIR / 'keys' / 'jwt_public.pem'))
    
    # Create keys directory
    os.makedirs(os.path.dirname(public_key_path), exist_ok=True)
    
    # Strategy 1: Try to read from shared volume
    if os.path.exists(public_key_path):
        try:
            with open(public_key_path, 'rb') as f:
                public_key = f.read()
            print(f'✅ JWT public key loaded from shared volume: {public_key_path}')
            return public_key
        except Exception as e:
            print(f'⚠️  Failed to read public key from volume: {e}')
    
    # Strategy 2: Fetch from UserService HTTP endpoint with retry
    max_retries = 5
    retry_delay = 2  # seconds
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f'🔄 Fetching public key from UserService (attempt {attempt}/{max_retries})...')
            response = requests.get(
                f'{user_service_url}/api/users/public-key/',
                timeout=5
            )
            response.raise_for_status()
            
            public_key = response.json()['public_key'].encode('utf-8')
            
            # Save to local file for future use
            try:
                with open(public_key_path, 'wb') as f:
                    f.write(public_key)
                print(f'✅ JWT public key fetched and saved to {public_key_path}')
            except Exception as e:
                print(f'⚠️  Could not save public key to file: {e}')
            
            print('  Algorithm: RS256')
            print('  ProductService can now verify JWT tokens locally!')
            
            return public_key
            
        except requests.exceptions.RequestException as e:
            print(f'❌ Attempt {attempt} failed: {e}')
            if attempt < max_retries:
                print(f'   Retrying in {retry_delay} seconds...')
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                print(f'❌ Failed to fetch public key after {max_retries} attempts')
    
    # Strategy 3: Return None and log warning
    print('⚠️  WARNING: Could not load JWT public key!')
    print('   Authentication will not work until key is available.')
    print('   Service will start in degraded mode.')
    return None

# Fetch public key on startup
JWT_PUBLIC_KEY_PEM = fetch_public_key_from_user_service()
if not JWT_PUBLIC_KEY_PEM and not DEBUG:
    raise ImproperlyConfigured('JWT public key is required when DEBUG=False')

# ============================================================================
# Django REST Framework Configuration
# ============================================================================

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
}

# ============================================================================
# JWT Configuration for Token VERIFICATION (not signing)
# Educational Note: ProductService only VERIFIES tokens, doesn't sign them
# ============================================================================

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    
    # Educational Note: We only need VERIFYING_KEY (public key)
    # No SIGNING_KEY because ProductService doesn't sign tokens
    'ALGORITHM': 'RS256',
    'VERIFYING_KEY': JWT_PUBLIC_KEY_PEM,  # Public key for verification
    # No SIGNING_KEY - this service only verifies, doesn't sign
    
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'false').lower() in {'1', 'true', 'yes', 'on'}
SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '0' if DEBUG else '31536000'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = True

# ============================================================================
# API Documentation (Swagger/OpenAPI)
# ============================================================================

SPECTACULAR_SETTINGS = {
    'TITLE': 'ProductService API',
    'DESCRIPTION': 'Product catalog and inventory management service',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
}

# ============================================================================
# Logging Configuration
# ============================================================================

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'products': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
