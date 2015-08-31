from django import template
from django.conf import settings

register = template.Library()

ALLOWABLE_VALUES = ("GITSERVER_GITHUB", "GITSERVER_GITLAB", "GITSERVER_BITBUCKET", "INSTALLED_GITSERVERS")

# settings value
@register.assignment_tag
def settings_value(name):
  if name in ALLOWABLE_VALUES:
    return getattr(settings, name, '')
  return ''
