
# Copyright 2016 Battelle Energy Alliance, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import unicode_literals, absolute_import
from django.conf import settings
from django.db import transaction
from ci.recipe import RecipeRepoReader, file_utils
from ci import models

class RecipeCreator(object):
    """
    Takes a list of recipe dicts and creates records in the database.
    """
    def __init__(self, recipes_dir):
        super(RecipeCreator, self).__init__()
        self._recipes_dir = recipes_dir
        self._sorted_recipes = {}
        self._repo_reader = None
        self._load_reader()
        self._sort_recipes()
        self._recipe_repo_rec = models.RecipeRepository.load()
        self._repo_sha = file_utils.get_repo_sha(self._recipes_dir)

        self._priority_map = {models.Recipe.CAUSE_PULL_REQUEST: "priority_pull_request",
                models.Recipe.CAUSE_PULL_REQUEST_ALT: "priority_pull_request",
                models.Recipe.CAUSE_PUSH: "priority_push",
                models.Recipe.CAUSE_MANUAL: "priority_manual",
                models.Recipe.CAUSE_RELEASE: "priority_release",
                }
        self._depends_map = {
                models.Recipe.CAUSE_PULL_REQUEST: {"key": "pullrequest_dependencies"},
                models.Recipe.CAUSE_PULL_REQUEST_ALT:
                    {"key": "pullrequest_dependencies", "dep_cause": models.Recipe.CAUSE_PULL_REQUEST},
                models.Recipe.CAUSE_PUSH: {"key": "push_dependencies"},
                models.Recipe.CAUSE_MANUAL: {"key": "manual_dependencies"},
                models.Recipe.CAUSE_RELEASE: {"key": "release_dependencies"},
                }

    def _load_reader(self):
        """
        Try load load all the recipes from the recipes directory.
        """
        try:
            self._repo_reader = RecipeRepoReader.RecipeRepoReader(self._recipes_dir)
        except Exception as e:
            print("Failed to load RecipeRepoReader: %s" % e)
            raise e

    def _sort_recipes(self):
        """
        Get the recipes that RecipeRepoReader has and sort them.
        """
        self._sorted_recipes = {}
        self._recipes_by_filename = {}
        for recipe in self._repo_reader.recipes:
            server_dict = self._sorted_recipes.get(recipe["repository_server"], {})
            user_dict = server_dict.get(recipe["build_user"], {})
            owner_dict = user_dict.get(recipe["repository_owner"], {})
            repo_list = owner_dict.get(recipe["repository_name"], [])
            repo_list.append(recipe)
            owner_dict[recipe["repository_name"]] = repo_list
            user_dict[recipe["repository_owner"]] = owner_dict
            server_dict[recipe["build_user"]] = user_dict
            self._sorted_recipes[recipe["repository_server"]] = server_dict
            self._recipes_by_filename[recipe["filename"]] = recipe

    def _update_repo_recipes(self, recipes, build_user, repo, dryrun=False):
        """
        Updates the recipes for a repository
        We break the recipes into 3 categories: no longer active, new, and changed.
        """
        current = models.Recipe.objects.filter(current=True, repository=repo)
        current_data = {}
        current_filenames = set()
        for r in current.all():
            current_filenames.add(r.filename)
            current_data[r.filename] = r.filename_sha

        new_files= set()
        changed_files = set()
        new_data = {}
        all_filenames = set()
        for recipe in recipes:
            fname = recipe["filename"]
            fname_sha = current_data.get(fname)
            all_filenames.add(fname)
            if fname_sha is not None:
                if fname_sha != recipe["sha"]:
                    # Note that multiple recipes might have the same filename/SHA
                    # but only differ in the CAUSE
                    changed_files.add(fname)
                    new_data[fname] = {"recipe": recipe}
            else:
                new_files.add(fname)
                new_data[fname] = {"recipe": recipe}

        to_remove = current_filenames - all_filenames
        if to_remove:
            print("\tNo longer active:\n\t\t%s" % "\n\t\t".join(sorted(to_remove)))
        if new_files:
            print("\tNew recipes:\n\t\t%s" % "\n\t\t".join(sorted(new_files)))
        if changed_files:
            print("\tChanged recipes:\n\t\t%s" % "\n\t\t".join(sorted(changed_files)))

        if not dryrun:
            for fname in to_remove:
                q = models.Recipe.objects.filter(current=True, filename=fname)
                q.filter(jobs=None).delete()
                q.update(current=False)

            all_files = new_files | changed_files

            for fname in all_files:
                recipe = new_data[fname]["recipe"]
                r_q = models.Recipe.objects.filter(filename=fname, current=True)
                r_q.filter(jobs=None).delete()
                r_q.update(current=False)

                self._process_recipe(recipe, build_user, repo)

            for fname in all_files:
                recipe = new_data[fname]["recipe"]
                self._update_depends(recipe, recipes)

        return len(to_remove), len(new_files), len(changed_files)

    def _process_recipe(self, recipe, build_user, repo):
        if recipe["trigger_pull_request"]:
            self._create_recipe(recipe, build_user, repo, None, models.Recipe.CAUSE_PULL_REQUEST)
        if recipe["allow_on_pr"] and not recipe["trigger_pull_request"]:
            self._create_recipe(recipe, build_user, repo, None, models.Recipe.CAUSE_PULL_REQUEST_ALT)
        if recipe["trigger_push"] and recipe["trigger_push_branch"]:
            branch, created = models.Branch.objects.get_or_create(name=recipe["trigger_push_branch"], repository=repo)
            self._create_recipe(recipe, build_user, repo, branch, models.Recipe.CAUSE_PUSH)
        if recipe["trigger_manual"] and recipe["trigger_manual_branch"]:
            branch, created = models.Branch.objects.get_or_create(name=recipe["trigger_manual_branch"], repository=repo)
            self._create_recipe(recipe, build_user, repo, branch, models.Recipe.CAUSE_MANUAL)
        if recipe["trigger_release"]:
            self._create_recipe(recipe, build_user, repo, None, models.Recipe.CAUSE_RELEASE)

    @transaction.atomic
    def load_recipes(self, force=False, dryrun=False):
        """
        Goes through all the recipes on disk and creates recipes in the database.
        Since there are various checks that are done, this is an atomic operation
        so that we can roll back if something goes wrong.
        Input:
            force[bool]: Try to reload the recipes, ignoring if the repo SHA hasn't changed
            dryrun[bool]: Don't actually create the recipes
        Exceptions:
          RecipeRepoReader.InvalidRecipe for a bad recipe
          RecipeRepoReader.InvalidDependency if a recipe has a bad dependency
        Return:
            tuple(int, int, int): (removed, new, changed)
        """
        print("%s reading recipes from %s %s" % ("-"*20, self._recipes_dir, "-"*20))

        if not force and self._repo_sha == self._recipe_repo_rec.sha:
            print("Repo the same, not loading recipes: %s" % self._repo_sha[:8])
            return 0, 0, 0

        removed = 0
        new = 0
        changed = 0
        for server in settings.INSTALLED_GITSERVERS:
            server_rec, created = models.GitServer.objects.get_or_create(host_type=server["type"], name=server["hostname"])
            for build_user, owners_dict in self._sorted_recipes.get(server_rec.name, {}).items():
                build_user_rec, created = models.GitUser.objects.get_or_create(name=build_user, server=server_rec)
                for owner, repo_dict in owners_dict.items():
                    owner_rec, created = models.GitUser.objects.get_or_create(name=owner, server=server_rec)
                    for repo, recipes in repo_dict.items():
                        repo_rec, created = models.Repository.objects.get_or_create(name=repo, user=owner_rec)
                        print("%s: %s:%s" % (build_user_rec, server_rec, repo_rec))
                        r, n, c = self._update_repo_recipes(recipes, build_user_rec, repo_rec, dryrun)
                        removed += r
                        new += n
                        changed += c

        if not dryrun:
            self._recipe_repo_rec.sha = self._repo_sha
            self._recipe_repo_rec.save()
            self._update_pull_requests()
        return removed, new, changed

    def install_webhooks(self):
        """
        Updates the webhooks on all the repositories.
        """
        for server in settings.INSTALLED_GITSERVERS:
            server_rec, created = models.GitServer.objects.get_or_create(host_type=server["type"], name=server["hostname"])
            if not server_rec.server_config().get("install_webhook", False):
                print("Not trying to install/update webhooks for %s" % server_rec)
                continue

            for build_user, owners_dict in self._sorted_recipes.get(server_rec.name, {}).items():
                build_user_rec, created = models.GitUser.objects.get_or_create(name=build_user, server=server_rec)
                api = build_user_rec.api()
                for owner, repo_dict in owners_dict.items():
                    owner_rec, created = models.GitUser.objects.get_or_create(name=owner, server=server_rec)
                    for repo, recipes in repo_dict.items():
                        repo_rec, created = models.Repository.objects.get_or_create(name=repo, user=owner_rec)
                        try:
                            api.install_webhooks(build_user_rec, repo_rec)
                            print("Webhook in place for %s" % repo_rec)
                        except Exception as e:
                            # We might not have direct access to install a webhook, which is fine
                            # if the repo is owned by non INL
                            print("FAILED to install webhook for %s:\n%s" % (repo_rec, e))

    def _get_new_recipe(self, recipe, build_user, repo, branch, cause):
        recipe_rec, created = models.Recipe.objects.get_or_create(
            filename=recipe["filename"],
            filename_sha=recipe["sha"],
            build_user=build_user,
            repository=repo,
            branch=branch,
            cause=cause,
            scheduler=recipe['scheduler']
            )
        recipe_rec.name = recipe["name"]
        recipe_rec.name = recipe["display_name"]
        recipe_rec.current = True
        recipe_rec.help_text = recipe["help"]
        recipe_rec.save()
        # This shouldn't really be needed, but just to be sure
        recipe_rec.depends_on.clear()
        return recipe_rec, created

    def _create_recipe(self, recipe, build_user, repo, branch, cause):
        """
        Creates the recipe in the database along with some of it many to many fields.
        We don't set the recipe dependency here because we need all recipes to be
        created first.
        Input:
          recipe: dict: As created by RecipeReader
          build_user: models.GitUser: Owner of the recipe
          repo: models.Repository: repository that the recipe is attached to
          branch: models.Branch: branch that the recipe is attached to or None if a PR
          cause: models.Recipe.CAUSE_* to specify the trigger for this recipe
        Return:
          models.Recipe that corresponds to the recipe dict
        """
        recipe_rec, created = self._get_new_recipe(recipe, build_user, repo, branch, cause)
        if not created:
            # We base things on file SHAs, so we could have reverted
            # back to a recipe that is not current.
            # We don't need to create all the steps/environment because
            # it should already exist
            return recipe_rec

        self._set_recipe(recipe_rec, recipe, cause)
        for step in recipe["steps"]:
            self._create_step(recipe_rec, step)
        self._create_recipe_env(recipe_rec, recipe)
        self._create_prestep(recipe_rec, recipe)
        return recipe_rec

    def _create_step(self, recipe_rec, step_dict):
        """
        Create a step and its environment.
        Input:
          recipe_rec: models.Recipe: Recipe to attach step to.
          step_dict: dict: A step dictionary as produced by RecipeReader in recipe["steps"]
        Return:
          models.Step
        """
        step_rec, created = models.Step.objects.get_or_create(recipe=recipe_rec,
            name=step_dict["name"],
            filename=step_dict["script"],
            position=step_dict["position"],
            abort_on_failure=step_dict["abort_on_failure"],
            allowed_to_fail=step_dict["allowed_to_fail"],
            )
        if created:
            for name, value in step_dict["environment"].items():
                step_env, created = models.StepEnvironment.objects.get_or_create(step=step_rec, name=name, value=value)
        return step_rec

    def _create_recipe_env(self, recipe_rec, recipe_dict):
        """
        Create the recipe environment.
        Input:
          recipe_rec: models.Recipe: Recipe to attach step to.
          recipe_dict: dict: A recipe dictionary as produced by RecipeReader
        """
        for name, value in recipe_dict["global_env"].items():
            recipe_env, created = models.RecipeEnvironment.objects.get_or_create(recipe=recipe_rec, name=name, value=value)

    def _create_prestep(self, recipe_rec, recipe_dict):
        """
        Create the recipe prestep sources.
        Input:
          recipe_rec: models.Recipe: Recipe to attach step to.
          recipe_dict: dict: A recipe dictionary as produced by RecipeReader
        """
        for source in recipe_dict["global_sources"]:
            recipe_source, created = models.PreStepSource.objects.get_or_create(recipe=recipe_rec, filename=source)

    def _update_depends(self, recipe, repo_recipes):
        for cause in models.Recipe.CAUSE_CHOICES:
            self._set_recipe_depends(recipe, cause[0])
            self._set_recipe_depends_reverse(recipe, repo_recipes, cause[0])

    def _set_recipe_depends(self, recipe, cause):
        """
        Set what recipes that this recipe depends on.
        We have a "cause" and a "dep_cause" to handle the case
        where this recipe is a "allow_on_pr" and it depends on
        a regular PR recipe.
        """
        fname = recipe["filename"]
        try:
            recipe_rec = models.Recipe.objects.get(filename=fname, current=True, cause=cause)
        except models.Recipe.DoesNotExist:
            return True

        info = self._depends_map[cause]
        dep_cause = info.get("dep_cause", cause)
        dep_key = info["key"]

        for dep in recipe[dep_key]:
            try:
                dep_rec = models.Recipe.objects.get(filename=dep, current=True, cause=dep_cause)
                recipe_rec.depends_on.add(dep_rec)
            except models.Recipe.DoesNotExist:
                raise RecipeRepoReader.InvalidDependency("Invalid dependency: %s -> %s" % (fname, dep))

    def _set_recipe_depends_reverse(self, recipe, repo_recipes, cause):
        """
        We need to update the recipes that depend on this recipe to use the new record.
        Many of those recipes havent' changed so we just look at all of them
        Input:
          recipe[dict]: Dictionary of recipe data as read by RecipeReader
          repo_recipes[list]: List of all recipes
          cause[models.Recipe.CAUSE*]: The recipe cause type
        """
        self._set_recipe_depends(recipe, cause)

        info = self._depends_map[cause]
        dep_cause = info.get("dep_cause", cause)
        dep_key = info["key"]

        fname = recipe["filename"]
        try:
            recipe_rec = models.Recipe.objects.get(filename=fname, current=True, cause=dep_cause)
        except models.Recipe.DoesNotExist:
            return True

        for parent in repo_recipes:
            if fname in parent[dep_key]:
                pfname = parent["filename"]
                try:
                    parent_rec = models.Recipe.objects.get(filename=pfname, current=True, cause=cause)
                except models.Recipe.DoesNotExist:
                    # Recipe with that cause doesn't exist, no problem
                    continue

                try:
                    old_rec = parent_rec.depends_on.get(filename=fname, current=False, cause=dep_cause)
                    parent_rec.depends_on.remove(old_rec)
                except models.Recipe.DoesNotExist:
                    # no problem. The recipe could have been already deleted due to not having jobs
                    pass
                parent_rec.depends_on.add(recipe_rec)

    def _update_pull_requests(self):
        """
        Update all PRs to use the latest version of alternate recipes.
        """
        for pr in models.PullRequest.objects.exclude(alternate_recipes=None).prefetch_related("alternate_recipes").all():
            new_alt = []
            for alt in pr.alternate_recipes.all():
                try:
                    recipe_rec = models.Recipe.objects.get(filename=alt.filename, current=True, cause=alt.cause)
                    new_alt.append(recipe_rec)
                except models.Recipe.DoesNotExist:
                    # no problem, maybe it doesn't exist any more
                    pass
            pr.alternate_recipes.clear()
            for r in new_alt:
                pr.alternate_recipes.add(r)

    def _set_recipe(self, recipe, recipe_dict, cause):
        """
        Set various fields on the models.Recipe based on the recipe dict.
        Input:
          recipe: models.Recipe to set
          recipe_dict: dict of the recipe
          cause: models.Recipe.CAUSE*
        """
        recipe.name = recipe_dict["name"]
        recipe.display_name = recipe_dict["display_name"]
        recipe.filename = recipe_dict["filename"]
        recipe.filename_sha = recipe_dict["sha"]
        recipe.active = recipe_dict["active"]
        recipe.private = recipe_dict["private"]
        recipe.activate_label = recipe_dict["activate_label"]
        recipe.pr_base_ref_override = recipe_dict["pr_base_ref_override"]
        recipe.cause = cause

        recipe.priority = recipe_dict[self._priority_map[cause]]
        if cause == models.Recipe.CAUSE_PUSH:
            recipe.priority = recipe_dict["priority_push"]
            recipe.auto_cancel_on_push = recipe_dict["auto_cancel_on_new_push"]

        if cause not in [models.Recipe.CAUSE_PULL_REQUEST, models.Recipe.CAUSE_PULL_REQUEST_ALT]:
            recipe.create_issue_on_fail = recipe_dict["create_issue_on_fail"]
            recipe.create_issue_on_fail_message = recipe_dict["create_issue_on_fail_message"]
            recipe.create_issue_on_fail_new_comment = recipe_dict["create_issue_on_fail_new_comment"]

        autos = {"automatic": models.Recipe.FULL_AUTO,
                "manual": models.Recipe.MANUAL,
                "authorized": models.Recipe.AUTO_FOR_AUTHORIZED,
                }
        recipe.automatic = autos[recipe_dict["automatic"]]

        for config in recipe_dict["build_configs"]:
            bc, created = models.BuildConfig.objects.get_or_create(name=config)
            recipe.build_configs.add(bc)

        for team in recipe_dict["viewable_by_teams"]:
            t, created = models.RecipeViewableByTeam.objects.get_or_create(team=team, recipe=recipe)

        if recipe_dict["client_runner_user"]:
            client_runner_user_rec, created = models.GitUser.objects.get_or_create(name=recipe_dict["client_runner_user"],
                    server=recipe.build_user.server)
            recipe.client_runner_user = client_runner_user_rec

        recipe.save()
