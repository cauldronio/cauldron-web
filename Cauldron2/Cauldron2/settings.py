import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRET_KEY = 'SECRET_DJANGO_KEY'

# GitHub Oauth keys
GH_CLIENT_ID = ''
GH_CLIENT_SECRET = ''

# GitLab Oauth keys
GL_CLIENT_ID = ''
GL_CLIENT_SECRET = ''

# Meetup Oauth keys
MEETUP_CLIENT_ID = ''
MEETUP_CLIENT_SECRET = ''

# ElasticSearch info
ES_IN_HOST = 'localhost?'
ES_IN_PORT = '9200'
ES_IN_PROTO = 'https'
ES_ADMIN_PASSWORD = 'admin'

# Kiban info
KIB_IN_HOST = ''
KIB_IN_PORT = ''
KIB_PATH = ''
KIB_IN_PROTO = ''
KIB_OUT_URL = ''

MATOMO_ENABLED = False
MATOMO_URL = ''

HATSTALL_ENABLED = False

GOOGLE_ANALYTICS_ID = ''

CAULDRON_ADMINS = {
    'GITHUB': [],
    'GITLAB': [],
    'MEETUP': [],
}

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'profile.apps.ProfileConfig',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'CauldronApp.apps.CauldronAppConfig',
    'metrics.apps.MetricsConfig',
    'poolsched.apps.PoolschedConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'Cauldron2.urls'

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

WSGI_APPLICATION = 'Cauldron2.wsgi.application'

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.mysql',
#         'NAME': 'db_name',
#         'USER': 'db_user',
#         'PASSWORD': 'db_password',
#         'HOST': 'db_host',
#         'PORT': 'db_port',
#         'OPTIONS': {
#             'sql_mode': 'traditional'
#         },
#         'TEST': {
#             'CHARSET': 'utf8'
#         }
#     }
# }

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
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

USE_L10N = True

USE_TZ = True

LOGIN_URL = 'homepage'

STATIC_URL = '/static/'
