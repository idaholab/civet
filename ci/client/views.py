# Copyright 2016-2025 Battelle Energy Alliance, LLC
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
from django.views.decorators.csrf import csrf_exempt
from django.http import (
    JsonResponse,
    HttpResponseNotAllowed,
    HttpResponseBadRequest,
    Http404,
)
import ipaddress
import json
from ci import models, views, Permissions
from ci.recipe import file_utils
import logging
from django.conf import settings
from datetime import timedelta
from ci.client import UpdateRemoteStatus
from django.shortcuts import render, redirect, get_object_or_404
from django.core.cache import cache
from .ReadyJobs import get_ready_jobs
from datetime import datetime
from django.db import transaction

logger = logging.getLogger("ci")

# Key in the cache used for storing the polled jobs. It was changed when
# the format of the entries changed, so that old entries aren't used.
CACHED_JOBS_KEY = "cached_jobs_by_user"


def get_client_ip(request):
    """
    Gets the address that a request came from.
    Behind reverse proxies, REMOTE_ADDR is the last proxy, and each proxy
    adds the address it got the request from to the end of X-Forwarded-For.
    Anything before those entries was sent by the client and can't be
    trusted, so the entry is counted from the end, by the number of
    proxies in settings.CLIENT_IP_TRUSTED_PROXIES. With 0, there is no
    proxy and X-Forwarded-For is ignored.
    Return:
      str: the normalized address, or None if it isn't a valid address
    """
    num_proxies = settings.CLIENT_IP_TRUSTED_PROXIES
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if num_proxies > 0 and x_forwarded_for:
        entries = x_forwarded_for.split(",")
        ip = entries[max(len(entries) - num_proxies, 0)].strip()
    else:
        ip = request.META.get("REMOTE_ADDR")
    try:
        return str(ipaddress.ip_address(ip))
    except ValueError:
        return None


def authenticate_client(request, data, client_name):
    """
    Finds the registered client that sent a request by the key in it.
    The name in the request must be the client's, and the request must
    come from the client's address. If the client doesn't have an address
    yet, it gets this one.
    Input:
      request[HttpRequest]: the request
      data[dict]: the JSON data in the request
      client_name[str]: the name that the client sent
    Return:
      (models.Client, None) if the client is authenticated, otherwise
      (None, HttpResponseBadRequest)
    """
    ip = get_client_ip(request)
    client = models.Client.get_by_build_key(data.get("build_key"))
    error = None
    if client is None:
        error = "Client %s at %s sent an invalid build key" % (client_name, ip)
    elif client.name != client_name:
        error = "Client %s at %s sent the build key for %s" % (
            client_name,
            ip,
            client.name,
        )
    elif ip is None:
        error = "Client %s sent a request from an invalid address" % client.name
    else:
        if client.ip is None:
            # Only set it if it is still not set, in case another
            # request set it in the meantime
            if models.Client.objects.filter(pk=client.pk, ip=None).update(ip=ip):
                logger.info("Client %s is now pinned to %s" % (client.name, ip))
            client.refresh_from_db(fields=["ip"])
        if client.ip != ip:
            error = "Client %s sent a request from %s instead of %s" % (
                client.name,
                ip,
                client.ip,
            )

    if error:
        logger.warning(error)
        return None, HttpResponseBadRequest("Invalid client")
    return client, None


def save_client_status(client):
    """
    Saves only the status fields of a client. A plain save() of a stale
    instance would overwrite fields changed elsewhere, like disabled.
    The status message is truncated to fit its column, since it can
    contain long recipe, config, and step names.
    """
    max_length = models.Client._meta.get_field("status_message").max_length
    client.status_message = client.status_message[:max_length]
    client.save(update_fields=["status", "status_message", "last_seen"])


def update_cached_jobs():
    logger.info("Rebuilding ready job cache")
    cached_jobs = {"expires": None, "jobs_by_config": {}}
    jobs_by_config = cached_jobs.get("jobs_by_config")
    ready_jobs = 0
    for job in get_ready_jobs():
        entry = {
            "pk": job.pk,
            "build_user": job.recipe.build_user_id,
            "client": job.client_id,
        }

        if job.config.name not in jobs_by_config:
            jobs_by_config[job.config.name] = []
        jobs_by_config[job.config.name].append(entry)
        ready_jobs += 1

    logger.info(f"Job cache rebuilt with {ready_jobs} ready job(s)")
    cached_jobs["expires"] = (
        datetime.now().timestamp() + settings.GET_JOB_UPDATE_INTERVAL / 1000
    )
    cache.set(CACHED_JOBS_KEY, cached_jobs)

    return cached_jobs


def client_is_disabled(client):
    """
    Reads whether the client is disabled from the database, locking its row
    for the rest of the transaction.
    """
    return (
        models.Client.objects.select_for_update()
        .values_list("disabled", flat=True)
        .get(pk=client.pk)
    )


@transaction.atomic(durable=True)
def get_cached_job(client, build_user_ids, build_configs):
    """
    Claims a ready job for the client.
    Input:
      client[models.Client]: the client asking for a job
      build_user_ids[set]: IDs of the build users whose jobs the client can run
      build_configs[list]: the build configs the client can run, in order of priority
    Return:
      (models.Job, dict): the claimed job and its info, or (None, None)
    """
    # For thread locking if we have a cache that supports it
    lock_context = None
    if hasattr(cache, "lock"):
        acquire_timeout = 2
        lock_context = cache.lock(
            "get_cached_job_lock", blocking_timeout=acquire_timeout
        )

    def run_locked():
        job_info = None
        job = None

        # The client could have been disabled since it was loaded. Lock its
        # row until the claim commits so that a disable can't race with it.
        # Store the fresh value so that the caller can see why no job was
        # claimed without reading it again.
        client.disabled = client_is_disabled(client)
        if client.disabled:
            return None, None

        cached_jobs = cache.get(CACHED_JOBS_KEY)
        rebuild_cache = False
        now = datetime.now().timestamp()
        if cached_jobs is None:
            logger.info("Rebuilding job cache as it is not yet built")
            rebuild_cache = True
        elif cached_jobs["expires"] <= now:
            logger.info("Rebuilding job cache because it is expired")
            rebuild_cache = True
        if rebuild_cache:
            cached_jobs = update_cached_jobs()

        # Sort through the cached jobs by our build configs; this lets
        # a client prioritize build config. That is, if any jobs exist
        # with the first config, they will take priority. Then the second,
        # and so on
        jobs_by_config = cached_jobs["jobs_by_config"]
        for build_config in build_configs:
            # No jobs by this config found
            if build_config not in jobs_by_config:
                continue

            jobs = jobs_by_config[build_config]
            for job_i in range(len(jobs)):
                job_entry = jobs[job_i]
                # Job isn't for one of this client's build users
                if job_entry["build_user"] not in build_user_ids:
                    continue
                # Job has a client set and it's not this one
                if job_entry["client"] is not None and job_entry["client"] != client.pk:
                    continue

                job = models.Job.objects.select_related(
                    "config", "client", "recipe", "event"
                ).get(pk=job_entry["pk"])

                if job.status != models.JobStatus.NOT_STARTED:
                    logger.warning(f"Job {job.pk} is cached but has already started")
                    job = None
                    continue
                if (
                    job.config.name != build_config
                    or job.recipe.build_user_id != job_entry["build_user"]
                    or job.client_id != job_entry["client"]
                ):
                    logger.warning(f"Job {job.pk} is in different state than cache")
                    job = None
                    continue

                job_info = get_job_info(job)
                job.client = client
                job.client_finished = False
                job.set_status(models.JobStatus.RUNNING)  # will save

                # Remove this job from being available in the cache
                del cached_jobs["jobs_by_config"][build_config][job_i]
                cache.set(CACHED_JOBS_KEY, cached_jobs)

                break

            if job:
                break

        return job, job_info

    if lock_context is None:
        return run_locked()
    else:
        from redis.exceptions import LockError

        try:
            with lock_context:
                return run_locked()
        except LockError:
            logger.warning(f"Failed to acquire cached job lock for {client.name}")

    return None, None


def disabled_client_response(client):
    """
    The response to a disabled client asking for a job. To the client,
    this looks the same as there being no jobs available.
    """
    client.status = models.Client.IDLE
    client.status_message = "Disabled; not accepting jobs"
    save_client_status(client)
    return json_claim_response(None, None, None, "Client is disabled", None)


@csrf_exempt
def get_job(request):
    data, response = check_post(request, ["client_name", "build_key", "build_configs"])
    if response is not None:
        return response

    client_name = data.get("client_name")
    client, response = authenticate_client(request, data, client_name)
    if response is not None:
        return response

    build_configs = data.get("build_configs")
    build_user_ids = set(client.build_users.values_list("pk", flat=True))

    # if a client is talking to us here then if they have any running jobs assigned to them they need
    # to be canceled. Only cancel the jobs of the client's build users.
    past_running_jobs = models.Job.objects.filter(
        recipe__build_user__in=build_user_ids,
        client=client,
        complete=False,
        status=models.JobStatus.RUNNING,
    )
    msg = "Canceled due to its client not finishing the job"
    for j in past_running_jobs.all():
        views.set_job_canceled(j, msg, client=client)
        UpdateRemoteStatus.job_complete(j)

    if client.disabled:
        return disabled_client_response(client)

    client.status_message = "Looking for work"
    client.status = models.Client.IDLE
    save_client_status(client)

    # This is atomic
    job, job_info = get_cached_job(client, build_user_ids, build_configs)

    # No job found
    if job is None:
        # Set by get_cached_job if it found the client disabled
        if client.disabled:
            return disabled_client_response(client)
        return json_claim_response(None, None, None, None, None)

    # The client is now running
    client.status = models.Client.RUNNING
    client.status_message = "Job {}: {}".format(job.pk, job)
    save_client_status(client)

    logger.info(
        "Client %s got job %s: %s: on %s"
        % (client_name, job.pk, job, job.recipe.repository)
    )

    UpdateRemoteStatus.job_started(job)
    return json_claim_response(job.pk, job.config.name, True, "Success", job_info)


def check_post(request, required_keys):
    if request.method != "POST":
        return None, HttpResponseNotAllowed(["POST"])
    try:
        data = json.loads(request.body)
    except ValueError:
        return None, HttpResponseBadRequest("Invalid JSON")
    if not isinstance(data, dict):
        return None, HttpResponseBadRequest("Bad POST data")
    # Don't log the data; it has the client's key
    missing = set(required_keys) - set(data.keys())
    if missing:
        logger.debug("Bad POST data, missing: %s" % ", ".join(sorted(missing)))
        return data, HttpResponseBadRequest("Bad POST data")
    return data, None


def get_job_info(job):
    """
    Gather all the information required to run a job to
    send to a client.
    We do it like this because we don't want the chance
    of the user changing the recipe while a job is running
    and causing problems.
    """
    job_dict = {
        "recipe_name": job.recipe.name,
        "job_id": job.pk,
    }

    recipe_env = {
        "CIVET_JOB_ID": job.pk,
        "CIVET_RECIPE_NAME": job.recipe.name,
        "CIVET_RECIPE_ID": job.recipe.pk,
        "CIVET_COMMENTS_URL": str(job.event.comments_url),
        "CIVET_BASE_REPO": str(job.event.base.repo()),
        "CIVET_BASE_REF_ORIGINAL": job.event.base.branch.name,
        "CIVET_BASE_REF": job.event.base.branch.name,
        "CIVET_BASE_SHA": job.event.base.sha,
        "CIVET_BASE_SSH_URL": str(job.event.base.ssh_url),
        "CIVET_HEAD_REPO": str(job.event.head.repo()),
        "CIVET_HEAD_REF": job.event.head.branch.name,
        "CIVET_HEAD_SHA": job.event.head.sha,
        "CIVET_HEAD_SSH_URL": str(job.event.head.ssh_url),
        "CIVET_EVENT_CAUSE": job.recipe.cause_str(),
        "CIVET_EVENT_ID": job.event.pk,
        "CIVET_BUILD_CONFIG": job.config.name,
        "CIVET_INVALIDATED": str(job.invalidated),
        "CIVET_NUM_STEPS": "0",
    }

    if job.event.pull_request:
        recipe_env["CIVET_PR_NUM"] = str(job.event.pull_request.number)
        if job.recipe.pr_base_ref_override:
            recipe_env["CIVET_BASE_REF"] = job.recipe.pr_base_ref_override
    else:
        recipe_env["CIVET_PR_NUM"] = "0"

    for env in job.recipe.environment_vars.all():
        recipe_env[env.name] = env.value

    job_dict["environment"] = recipe_env

    base_file_dir = settings.RECIPE_BASE_DIR
    prestep_env = []
    for prestep in job.recipe.prestepsources.all():
        if prestep.filename:
            contents = file_utils.get_contents(base_file_dir, prestep.filename)
            if contents:
                prestep_env.append(contents)

    job_dict["prestep_sources"] = prestep_env

    job.step_results.all().delete()
    step_recipes = []
    for step in job.recipe.steps.order_by("position"):
        step_dict = {
            "step_num": step.position,
            "step_position": step.position,
            "step_name": step.name,
            "abort_on_failure": step.abort_on_failure,
            "allowed_to_fail": step.allowed_to_fail,
        }

        step_result, created = models.StepResult.objects.get_or_create(
            job=job,
            name=step.name,
            position=step.position,
            abort_on_failure=step.abort_on_failure,
            allowed_to_fail=step.allowed_to_fail,
            filename=step.filename,
        )

        logger.info(
            "Created step result for {}: {}: {}: {}".format(
                job.pk, job, step_result.pk, step.name
            )
        )
        step_result.output = ""
        step_result.complete = False
        step_result.seconds = timedelta(seconds=0)
        step_result.status = models.JobStatus.NOT_STARTED
        step_result.save()
        step_dict["stepresult_id"] = step_result.pk

        step_env = {
            "CIVET_STEP_NUM": step_dict["step_num"],
            "CIVET_STEP_POSITION": step_dict["step_position"],
            "CIVET_STEP_NAME": step_dict["step_name"],
            "CIVET_STEP_ABORT_ON_FAILURE": step_dict["abort_on_failure"],
            "CIVET_STEP_ALLOWED_TO_FAIL": step_dict["allowed_to_fail"],
        }
        for env in step.step_environment.all():
            step_env[env.name] = env.value
        step_dict["environment"] = step_env

        if step.filename:
            contents = file_utils.get_contents(base_file_dir, step.filename)
            step_dict["script"] = str(contents)  # in case of empty file, use str

        step_recipes.append(step_dict)

    job_dict["environment"]["CIVET_NUM_STEPS"] = str(len(step_recipes))
    job_dict["steps"] = step_recipes
    job.recipe_repo_sha = file_utils.get_repo_sha(base_file_dir)
    job.save()

    return job_dict


def json_claim_response(job_id, config_name, claimed, msg, job_info=None):
    return JsonResponse(
        {
            "job_id": job_id,
            "config": config_name,
            "success": claimed,
            "message": msg,
            "status": "OK",
            "job_info": job_info,
        }
    )


class AfterResponseJsonResponse(JsonResponse):
    """
    A JsonResponse that calls a function after the response has been sent.
    The WSGI server calls close() once it has sent the response, so the
    client isn't kept waiting on slow work like updating the Git server.
    """

    def __init__(self, data, after_response, **kwargs):
        super().__init__(data, **kwargs)
        self._after_response = after_response

    def close(self):
        # This needs to happen before closing the response as that will
        # close the database connection
        try:
            self._after_response()
        except Exception:
            logger.exception("Error while running after response")
        finally:
            super().close()


def json_finished_response(status, msg, after_response=None):
    data = {"status": status, "message": msg}
    if after_response:
        return AfterResponseJsonResponse(data, after_response)
    return JsonResponse(data)


def check_job_finished_post(request, client_name, job_id):
    data, response = check_post(request, ["build_key", "seconds", "complete"])

    if response:
        return response, None, None, None

    client, response = authenticate_client(request, data, client_name)
    if response:
        return response, None, None, None

    # Only the client that claimed the job can update it
    try:
        job = models.Job.objects.get(pk=job_id, client=client)
    except models.Job.DoesNotExist:
        return HttpResponseBadRequest("Invalid job"), None, None, None

    return None, data, client, job


@csrf_exempt
def job_finished(request, client_name, job_id):
    """
    Called when all the steps in the job are finished or when a job fails and is not
    going to do anymore steps.
    Should be called for every job, no matter if it was canceled or failed.
    """
    response, data, client, job = check_job_finished_post(request, client_name, job_id)
    if response:
        return response

    if job.client_finished:
        # The client didn't get our response to a previous job_finished
        # (ie the request timed out) and is trying again. Don't process it
        # again; we would repeat all the Git server updates, like PR comments.
        logger.info(
            "Job %s: %s: ignoring repeated job_finished from %s"
            % (job.pk, job, client.name)
        )
        return json_finished_response("OK", "Success")

    job.running_step = ""
    job.seconds = timedelta(seconds=data["seconds"])
    job.complete = data["complete"]
    job.client_finished = True
    # In addition to the server sending the cancel command to the client, this
    # can also be set by the client if something went wrong
    if data.get("canceled", False):
        job.status = models.JobStatus.CANCELED
    job.save()
    job.event.save()  # update timestamp

    status = None
    # If the job is already set to canceled, we don't want to change it
    if job.status == models.JobStatus.CANCELED:
        status = job.status
    job.set_status(status=status, calc_event=True)

    client.status = models.Client.IDLE
    client.status_message = "Finished job {}: {}".format(job.pk, job)
    save_client_status(client)
    all_done = UpdateRemoteStatus.job_complete_local(job)
    if not all_done:
        job.event.make_jobs_ready()

    # Updating the Git server can take a while, so do it after we have
    # responded to the client so that it doesn't time out
    def update_remote():
        UpdateRemoteStatus.job_complete_remote(job, all_done)

    return json_finished_response("OK", "Success", after_response=update_remote)


def json_update_response(status, msg, cmd=None):
    """
    status: current status of the job
    msg: "success" so that the client knows everything was handled properly
    cmd : None or "cancel" if the job got canceled
    """
    data = {"status": status, "message": msg, "command": cmd}
    return JsonResponse(data)


def check_step_result_post(request, client_name, stepresult_id):
    data, response = check_post(
        request, ["build_key", "step_num", "output", "time", "complete", "exit_status"]
    )

    if response:
        return response, None, None, None

    client, response = authenticate_client(request, data, client_name)
    if response:
        return response, None, None, None

    # Only the client that claimed the job can update it
    try:
        step_result = models.StepResult.objects.select_related(
            "job",
            "job__event",
            "job__event__base__branch__repository",
            "job__client",
            "job__event__pull_request",
        ).get(pk=stepresult_id, job__client=client)
    except models.StepResult.DoesNotExist:
        return HttpResponseBadRequest("Invalid stepresult id"), None, None, None

    # The client has already called job_finished, so the results are final.
    # Note that job.complete isn't sufficient here; it is also set when the
    # job is canceled on the server, and the client still needs to update
    # its steps to be told about the cancel.
    if step_result.job.client_finished:
        return HttpResponseBadRequest("Job is already finished"), None, None, None
    return None, data, step_result, client


@csrf_exempt
def start_step_result(request, client_name, stepresult_id):
    response, data, step_result, client = check_step_result_post(
        request, client_name, stepresult_id
    )
    if response:
        return response

    cmd = None
    # could have been canceled in between getting the job and starting the job
    status = models.JobStatus.RUNNING
    if step_result.job.status == models.JobStatus.CANCELED:
        status = models.JobStatus.CANCELED
        cmd = "cancel"

    step_result.status = status
    step_result.job.running_step = "{}/{}".format(
        step_result.position + 1, step_result.job.step_results.count()
    )
    step_result.save()
    step_result.job.seconds = step_result.job.calc_total_time()
    step_result.job.save()  # update timestamp
    client.status_message = "Starting {} on job {}".format(
        step_result.name, step_result.job
    )
    save_client_status(client)
    step_result.job.event.save()  # update timestamp
    return json_update_response("OK", "success", cmd)


def save_step_result(step_result):
    try:
        step_result.save()
    except Exception as e:
        # We could potentially have bad output that causes errors when saving.
        # For example, on Postgresql:
        # ValueError: A string literal cannot contain NUL (0x00) characters.
        step_result.output = "Failed to save output:\n%s" % e
        step_result.save()


def step_result_from_data(step_result, data, status):
    step_result.seconds = timedelta(seconds=data["time"])
    step_result.output = step_result.output + data["output"]
    step_result.complete = data["complete"]
    step_result.exit_status = int(data["exit_status"])
    step_result.status = status
    save_step_result(step_result)


@csrf_exempt
def complete_step_result(request, client_name, stepresult_id):
    response, data, step_result, client = check_step_result_post(
        request, client_name, stepresult_id
    )
    if response:
        return response

    status = models.JobStatus.SUCCESS
    if data.get("canceled"):
        status = models.JobStatus.CANCELED
    elif data["exit_status"] == 85:
        status = models.JobStatus.INTERMITTENT_FAILURE
    elif data["exit_status"] == 86:
        status = models.JobStatus.SKIPPED
    elif data["exit_status"] != 0:
        if not step_result.job.failed_step:
            step_result.job.failed_step = step_result.name
            step_result.job.save()
        status = models.JobStatus.FAILED
        if step_result.allowed_to_fail:
            status = models.JobStatus.FAILED_OK

    step_result_from_data(step_result, data, status)

    step_result.job.seconds = step_result.job.calc_total_time()
    step_result.job.save()  # update timestamp
    step_result.job.event.save()  # update timestamp
    if data["complete"]:
        step_result.output = data["output"]
        save_step_result(step_result)

        client.status_message = "Completed {}: {}".format(
            step_result.job, step_result.name
        )
        save_client_status(client)

    return json_update_response("OK", "success")


@csrf_exempt
def update_step_result(request, client_name, stepresult_id):
    response, data, step_result, client = check_step_result_post(
        request, client_name, stepresult_id
    )
    if response:
        return response

    step_result_from_data(step_result, data, models.JobStatus.RUNNING)
    job = step_result.job

    cmd = None
    # somebody canceled or invalidated the job
    if (
        job.status == models.JobStatus.CANCELED
        or job.status == models.JobStatus.NOT_STARTED
    ):
        step_result.status = job.status
        step_result.save()
        cmd = "cancel"

    client.status_message = "Running {} ({}): {} : {}".format(
        step_result.job, step_result.job.pk, step_result.name, step_result.seconds
    )
    save_client_status(client)

    job.seconds = job.calc_total_time()
    job.save()
    job.event.save()  # update timestamp

    return json_update_response("OK", "success", cmd)


@csrf_exempt
def client_ping(request, client_name):
    data, response = check_post(request, ["build_key"])
    if response:
        return response

    client, response = authenticate_client(request, data, client_name)
    if response:
        return response

    client.status_message = "Running on another server"
    client.status = models.Client.RUNNING
    save_client_status(client)

    return json_update_response("OK", "success", "")


def update_remote_job_status(request, job_id):
    """
    End point for manually update the remote status of a job.
    This is needed since sometimes the git server doesn't
    get updated properly due to timeouts, etc.
    """
    job = get_object_or_404(models.Job.objects, pk=job_id)
    if not Permissions.can_view_repo(request.session, job.event.base.repo()):
        raise Http404()

    allowed = Permissions.is_collaborator(
        request.session, job.event.build_user, job.event.base.repo()
    )

    if request.method == "GET":
        return render(request, "ci/job_update.html", {"job": job, "allowed": allowed})
    elif request.method == "POST":
        if allowed:
            UpdateRemoteStatus.job_complete_status(job)
        else:
            return HttpResponseNotAllowed("Not allowed")
    return redirect("ci:view_job", job_id=job.pk)
