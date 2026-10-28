"""Seed the dev DB with a git server, repo, PR event and one ready job, using the test factories.

Run from the repo root (see SKILL.md). Prints the build_key and job id the client API needs.
"""

import django

django.setup()
from ci.tests import utils

# The name must match the hostname of a server in settings.INSTALLED_GITSERVERS,
# otherwise every page that checks permissions raises "Git server ... is not configured".
server = utils.create_git_server(name="github.com")
build_user = utils.create_user_with_token(name="moosebuild", server=server)
owner = utils.create_user(name="owner", server=server)
repo = utils.create_repo(name="demo", user=owner, active=True)
branch = utils.create_branch(name="devel", repo=repo)
pr = utils.create_pr(title="Demo PR", number=1, repo=repo)
ev = utils.create_event(user=build_user, branch1=branch, branch2=branch)
# /pr/<id>/ 404s for a PR without events, and the factory doesn't link them
ev.pull_request = pr
ev.save()
recipe = utils.create_recipe(user=build_user, repo=repo, branch=branch)
utils.create_step(recipe=recipe)
job = utils.create_job(recipe=recipe, event=ev)
job.ready = True
job.active = True
job.save()
print(
    "build_key=%s job_id=%s config=%s" % (build_user.build_key, job.pk, job.config.name)
)
