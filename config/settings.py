"""
Django settings for config project.
"""

from pathlib import Path
import environ
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False)
)
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG', default=False)

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['.vercel.app', 'localhost', '127.0.0.1'])

# Public origin. QStash calls back into this host, so it must be the real
# deployment URL, not localhost, in production.
SITE_URL = env('SITE_URL', default='http://127.0.0.1:8000')

# AI Settings
AI_PROVIDER = env('AI_PROVIDER', default='ollama')
DEEPSEEK_API_KEY = env('DEEPSEEK_API_KEY', default='')
DEEPSEEK_API_URL = env('DEEPSEEK_API_URL', default='https://api.deepseek.com/v1/chat/completions')
OLLAMA_URL = env('OLLAMA_URL', default='http://127.0.0.1:11434/api/generate')
OLLAMA_MODEL = env('OLLAMA_MODEL', default='phi3')
OCR_SPACE_API_KEY = env('OCR_SPACE_API_KEY', default='helloworld')
DELETE_ROOT_PASSWORD = env('DELETE_ROOT_PASSWORD', default='root')

# Background jobs — QStash (Upstash).
#
# Serverless has no long-lived worker, so the queue is HTTP-based: we publish a job
# and QStash calls a webhook back. Without QSTASH_TOKEN the job runs inline, which
# keeps local development and tests working with no external service.
QSTASH_TOKEN = env('QSTASH_TOKEN', default='')
QSTASH_URL = env('QSTASH_URL', default='https://qstash.upstash.io/v2/publish/')
# The webhook is public, so its signature must be verified. QStash rotates between
# these two keys, and both are accepted at any time.
QSTASH_CURRENT_SIGNING_KEY = env('QSTASH_CURRENT_SIGNING_KEY', default='')
QSTASH_NEXT_SIGNING_KEY = env('QSTASH_NEXT_SIGNING_KEY', default='')

# Security settings (enabled by default in production)
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=not DEBUG)
SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=not DEBUG)
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=not DEBUG)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Local apps
    'core',
    'accounting',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': env.db('DATABASE_URL', default=f'sqlite:///{BASE_DIR}/db.sqlite3')
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = 'media/'
MEDIA_ROOT = env('MEDIA_ROOT', default=str(BASE_DIR / 'media'))

# Uploaded statements must outlive the request that uploaded them: on Vercel the
# background job runs in a *different* invocation, and /tmp is not shared between
# invocations. So in production the file goes to object storage (S3 / Cloudflare R2).
# Local development falls back to the filesystem when no bucket is configured.
AWS_STORAGE_BUCKET_NAME = env('AWS_STORAGE_BUCKET_NAME', default='')
AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID', default='')
AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY', default='')
AWS_S3_ENDPOINT_URL = env('AWS_S3_ENDPOINT_URL', default='') or None  # set this for R2
AWS_S3_REGION_NAME = env('AWS_S3_REGION_NAME', default='auto')
AWS_DEFAULT_ACL = None
AWS_QUERYSTRING_AUTH = True  # statements are private; serve them via signed URLs
AWS_S3_FILE_OVERWRITE = False

if AWS_STORAGE_BUCKET_NAME:
    DEFAULT_FILE_STORAGE_BACKEND = 'storages.backends.s3boto3.S3Boto3Storage'
else:
    DEFAULT_FILE_STORAGE_BACKEND = 'django.core.files.storage.FileSystemStorage'

STORAGES = {
    'default': {'BACKEND': DEFAULT_FILE_STORAGE_BACKEND},
    # Plain backend, not whitenoise's manifest storage: the manifest only exists after
    # collectstatic, so requiring it breaks tests and any un-collected environment.
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'core.User'

LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'
