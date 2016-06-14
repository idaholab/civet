from django.conf.locale.en import formats as en_formats
"""
Django settings for civet project.

Generated by 'django-admin startproject' using Django 1.8.2.

For more information on this file, see
https://docs.djangoproject.com/en/1.8/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.8/ref/settings/
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.8/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '-85d^-^foncz90n+p7ap#irn1&$v*5%d!$u!w0m@w2v*m#&698'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# set to the hosts that urls will have in their names
ALLOWED_HOSTS = []

# Application definition

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'ci',
    'debug_toolbar',
    'sslserver',
)

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.security.SecurityMiddleware',
)

ROOT_URLCONF = 'civet.urls'

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

WSGI_APPLICATION = 'civet.wsgi.application'


# Database
# https://docs.djangoproject.com/en/1.8/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    },
#    'default': {
#        'ENGINE': 'django.db.backends.postgresql_psycopg2',
#        'NAME': '<db_name>',
#        'USER': 'postgres',
#        'PASSWORD': '<password>',
#        'HOST': 'localhost',
#        'PORT': '',
#        'CONN_MAX_AGE': 60,
#    }
}


# Internationalization
# https://docs.djangoproject.com/en/1.8/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True
en_formats.DATETIME_FORMAT = 'H:i:s m/d/y e'


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.8/howto/static-files/

STATIC_URL = '/static/'

# directory where all the static files go when
# calling ./manage.py collectstatic
STATIC_ROOT = BASE_DIR + '/static'

#DEFAULT_AUTHENTICATION_CLASSES = ( 'rest_framework.authentication.OAuth2Authentication',)
LOGGING = {
  'version': 1,
  'disable_existing_loggers': False,
  'formatters': {
    'simple': {
      'format': '%(asctime)s:%(levelname)s:%(message)s'
    },
    'verbose': {
      'format': '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'
    },
  },
  'handlers': {
    'file': {
      'level': 'DEBUG',
      'class': 'logging.FileHandler',
      'filename': 'civet.log',
      'formatter': 'simple',
      },
    'console':{
      'level':'DEBUG',
      'class':'logging.StreamHandler',
      'formatter': 'simple',
      },
    },
    'loggers': {
      'django.request': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
        'propagate': True,
      },
      'django': {
        'handlers':['console', 'file'],
        'propagate': True,
        'level':'INFO',
      },
      'ci': {
        'handlers':['console', 'file'],
        'propagate': True,
        'level':'DEBUG',
      },
    },
  }

#SECURE_CONTENT_TYPE_NOSNIFF=True
#SECURE_BROWSER_XSS_FILTER=True
#SECURE_SSL_REDIRECT=True
#SESSION_COOKIE_SECURE=True
#CSRF_COOKIE_SECURE=True
#CSRF_COOKIE_HTTPONLY=True
#X_FRAME_OPTIONS='DENY'
#SECURE_HSTS_SECONDS=

#location of the recipes directory, relative to the base project directory
RECIPE_BASE_DIR = BASE_DIR + '/../civet_recipes'

# all the git servers that we support
GITSERVER_GITHUB = 0
GITSERVER_GITLAB = 1
GITSERVER_BITBUCKET = 2

# flag used while testing. Prevents the update of
# comments and PR statuses.
REMOTE_UPDATE = False
# flag used while testing. Prevents installing
# a webhook when a recipe is created.
INSTALL_WEBHOOK = False

# Base URL for this server. This is used in building absolute URLs
# for web hooks on external servers. Ex. https://moosebuild.org
WEBHOOK_BASE_URL = '<URL>'

# supported gitservers
INSTALLED_GITSERVERS = [GITSERVER_GITHUB]

# These owners will be checked against when checking if a
# user can see job client information.
AUTHORIZED_OWNERS = ['idaholab']

# The client and secret given by GitHub
GITHUB_CLIENT_ID = '<client_id>'
GITHUB_SECRET_ID = '<secret_id>'

# We don't use the client_id/secret on GitLab since
# it doesn't seem to work with LDAP on our internal
# GitLab
GITLAB_API_URL = 'http://<gitlab hostname>'
GITLAB_HOSTNAME = '<gitlab hostname>'
# Setting this to false will cause SSL cert verification
# to be disabled when communicating with the GitLab server.
# Setting it to a filename of the cert of the server will enable
# verification with the added bonus of reducing the number
# of log messages.
GITLAB_SSL_CERT = False

# The client and secret given by BitBucket
BITBUCKET_CLIENT_ID = None
BITBUCKET_SECRET_ID = None

# GitHub Labels with this prefix will be removed when a PR branch is pushed to
GITHUB_REMOVE_PR_LABEL_PREFIX = ["PR: [TODO]"]

# If a GitHub PR has a title that starts with one of these then it
# will be ignored.
GITHUB_PR_WIP_PREFIX = ["WIP:", "[WIP]"]

# If a Gitlab PR has a title that starts with one of these then it
# will be ignored.
GITLAB_PR_WIP_PREFIX = ["WIP:", "[WIP]"]

# Instead of checking the Git server each time to check if the
# user is a collaborator on a repo, we cache the results
# for this amount of time. Once this has expired then we
# recheck.
COLLABORATOR_CACHE_TIMEOUT = 60*60

# The absolute url for the server. This is used
# in places where we need to send links to outside
# sources that will point to the server and we
# don't have access to a HttpRequest object.
ABSOLUTE_BASE_URL = "https://localhost"

# Interval (in milliseconds) in which the browser will do an AJAX call to update.
# Put here so that we can dynamically change these while testing
HOME_PAGE_UPDATE_INTERVAL = 20000
JOB_PAGE_UPDATE_INTERVAL = 15000
EVENT_PAGE_UPDATE_INTERVAL = 20000
