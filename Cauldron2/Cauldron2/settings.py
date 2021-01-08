import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Generated as Django does when creating a new project
SECRET_KEY = os.environ.get('SECRET_KEY')

# GitHub Oauth keys
GH_CLIENT_ID = os.environ.get('GH_CLIENT_ID')
GH_CLIENT_SECRET = os.environ.get('GH_CLIENT_SECRET')

# GitLab Oauth keys
GL_CLIENT_ID = os.environ.get('GL_CLIENT_ID')
GL_CLIENT_SECRET = os.environ.get('GL_CLIENT_SECRET')

# Meetup Oauth keys
MEETUP_CLIENT_ID = os.environ.get('MEETUP_CLIENT_ID')
MEETUP_CLIENT_SECRET = os.environ.get('MEETUP_CLIENT_SECRET')

# GNOME Oauth keys
GNOME_CLIENT_ID = os.environ.get('GNOME_CLIENT_ID')
GNOME_CLIENT_SECRET = os.environ.get('GNOME_CLIENT_SECRET')

# Webserver
CAULDRON_HOST = os.environ.get('CAULDRON_HOST')
CAULDRON_PORT = os.environ.get('CAULDRON_PORT')

# ElasticSearch
ES_IN_HOST = os.environ.get('ELASTIC_HOST')
ES_IN_PORT = os.environ.get('ELASTIC_PORT')
ES_IN_PROTO = os.environ.get('ELASTIC_PROTOCOL')
ES_ADMIN_PASSWORD = os.environ.get('ELASTIC_ADMIN_PASSWORD')

# Kibana
KIB_IN_HOST = os.environ.get('KIBANA_HOST')
KIB_IN_PORT = os.environ.get('KIBANA_PORT')
KIB_IN_PROTO = os.environ.get('KIBANA_PROTOCOL')
KIB_PATH = os.environ.get('KIBANA_URL_PATH')
KIB_OUT_URL = f'https://{CAULDRON_HOST}:{CAULDRON_PORT}{KIB_PATH}'

# Database
DB_NAME = os.environ.get('DB_NAME')
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_HOST = os.environ.get('DB_HOST')
DB_PORT = os.environ.get('DB_PORT')

# Matomo
MATOMO_ENABLED = os.environ.get('MATOMO_ENABLED')
MATOMO_PORT = os.environ.get('MATOMO_PORT')
MATOMO_URL = f'https://{CAULDRON_HOST}:{MATOMO_PORT}'

# Hatstall/Sortinghat
HATSTALL_ENABLED = os.environ.get('HATSTALL_ENABLED') in ('True', 'true')
SORTINGHAT = HATSTALL_ENABLED  # Just define the variable for some files

# Other
GOOGLE_ANALYTICS_ID = os.environ.get('GOOGLE_ANALYTICS_ID')

CAULDRON_ADMINS = {
    'GITHUB': json.loads(os.environ.get('GITHUB_ADMINS', '[]')),
    'GITLAB': json.loads(os.environ.get('GITLAB_ADMINS', '[]')),
    'MEETUP': json.loads(os.environ.get('MEETUP_ADMINS', '[]')),
    'GNOME': json.loads(os.environ.get('GNOME_ADMINS', '[]')),
}

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'CauldronApp.apps.CauldronAppConfig',
    'metrics.apps.MetricsConfig',
    'profile.apps.ProfileConfig',
    'poolsched',
    'cauldron_apps.cauldron',
    'cauldron_apps.poolsched_git',
    'cauldron_apps.poolsched_github',
    'cauldron_apps.poolsched_gitlab',
    'cauldron_apps.poolsched_meetup',
    'cauldron_apps.poolsched_export',
    'cauldron_apps.cauldron_actions',
]
if HATSTALL_ENABLED:
    INSTALLED_APPS.append('hatstall')
    INSTALLED_APPS.append('cauldron_apps.poolsched_autorefresh')
    INSTALLED_APPS.append('cauldron_apps.poolsched_merge_identities')

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
if HATSTALL_ENABLED:
    INSTALLED_APPS.append('Cauldron2.middleware.HatstallAuthorizationMiddleware')

ROOT_URLCONF = 'Cauldron2.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR + '/templates'],
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

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': DB_NAME,
        'USER': DB_USER,
        'PASSWORD': DB_PASSWORD,
        'HOST': DB_HOST,
        'PORT': DB_PORT,
        'OPTIONS': {
            'sql_mode': 'traditional'
        },
        'TEST': {
            'CHARSET': 'utf8'
        }
    }
}

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
#     }
# }

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
