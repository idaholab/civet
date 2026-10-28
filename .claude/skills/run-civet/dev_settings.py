# Local-only overlay on civet/settings.py so the server can run over plain HTTP.
# Used via: PYTHONPATH=.:.claude/skills/run-civet DJANGO_SETTINGS_MODULE=dev_settings
from civet import settings as base

globals().update({k: v for k, v in vars(base).items() if k.isupper()})

ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
SESSION_COOKIE_SECURE = False
ABSOLUTE_BASE_URL = "http://127.0.0.1:8765"

# Repos are only visible to anonymous viewers when active and public.
INSTALLED_GITSERVERS = [dict(base.github_config, public_default=True)]
