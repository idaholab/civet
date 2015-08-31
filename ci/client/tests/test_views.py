from django.test import TestCase, Client
from django.test.client import RequestFactory
from django.core.urlresolvers import reverse
from django.http import HttpResponseNotAllowed, HttpResponseBadRequest
import json
from mock import patch
from ci import models
from ci.client import views
from ci.recipe import file_utils
from ci.tests import utils

class ViewsTestCase(TestCase):
  fixtures = ['base']

  def setUp(self):
    self.client = Client()
    self.factory = RequestFactory()

  def test_client_ip(self):
    request = self.factory.get('/')
    request.META['REMOTE_ADDR'] = '1.1.1.1'
    ip = views.get_client_ip(request)
    self.assertEqual('1.1.1.1', ip)
    request.META['HTTP_X_FORWARDED_FOR'] = '2.2.2.2'
    ip = views.get_client_ip(request)
    self.assertEqual('2.2.2.2', ip)

  def test_ready_jobs(self):
    url = reverse('ci:client:ready_jobs', args=['123','linux-gnu', 'client'])
    # only get allowed
    response = self.client.post(url)
    self.assertEqual(response.status_code, 405) # not allowed

    # valid request, but no user with build key, so no jobs
    response = self.client.get(url)
    self.assertEqual(response.status_code, 200)
    data = json.loads(response.content)
    self.assertIn('jobs', data)
    self.assertEqual(len(data['jobs']), 0)

    user = utils.get_test_user()
    job = utils.create_job(user=user)
    job.ready = True
    job.active = True
    job.save()

    # valid request with a ready job
    url = reverse('ci:client:ready_jobs', args=[user.build_key, job.config.name, 'client'])
    response = self.client.get(url)
    self.assertEqual(response.status_code, 200)
    data = json.loads(response.content)
    self.assertIn('jobs', data)
    self.assertEqual(len(data['jobs']), 1)

  def json_post_request(self, data):
    jdata = json.dumps(data)
    return self.factory.post('/', jdata, content_type='application/json')

  def client_post_json(self, url, data):
    jdata = json.dumps(data)
    return self.client.post(url, jdata, content_type='application/json')

  def test_check_post(self):
    # only post allowed
    request = self.factory.get('/')
    required = ['foo',]
    data, response = views.check_post(request, required)
    self.assertEqual(data, None)
    self.assertTrue(isinstance(response, HttpResponseNotAllowed))

    # bad json decoding
    request = self.factory.post('/', {'bar': 'bar'}, content_type='text/html')
    data, response = views.check_post(request, required)
    self.assertEqual(data, None)
    self.assertTrue(isinstance(response, HttpResponseBadRequest))

    # should be successful
    request = self.json_post_request({'foo': 'bar'})
    data, response = views.check_post(request, required)
    self.assertNotEqual(data, None)
    self.assertEqual(None, response)

    # failed because we don't have the right data
    request = self.json_post_request({'bar': 'bar'})
    data, response = views.check_post(request, required)
    self.assertNotEqual(data, None)
    self.assertTrue(isinstance(response, HttpResponseBadRequest))

  @patch.object(file_utils, 'get_contents')
  def test_get_job_info(self, contents_mock):
    contents_mock.return_value = 'contents'
    user = utils.get_test_user()
    job = utils.create_job(user=user)
    utils.create_prestepsource(recipe=job.recipe)
    step = utils.create_step(recipe=job.recipe)
    utils.create_step_environment(step=step)
    utils.create_recipe_environment(recipe=job.recipe)
    data = views.get_job_info(job)
    self.assertIn('name', data)

  def test_claim_job(self):
    post_data = {'job_id': 0}
    user = utils.get_test_user()
    url = reverse('ci:client:claim_job', args=[user.build_key, 'testconfig', 'testClient'])

    # only post allowed
    response = self.client.get(url)
    self.assertEqual(response.status_code, 405) # not allowed

    # setup a ready job
    job = utils.create_job(user=user)
    job.ready = True
    job.active = True
    job.event.cause = models.Event.PULL_REQUEST
    job.event.save()
    job.status = models.JobStatus.NOT_STARTED
    job_id = job.pk
    job.save()

    # bad config
    post_data = {'job_id': job_id}
    response = self.client_post_json(url, post_data)
    self.assertEqual(response.status_code, 400) # bad request

   # config different than job
    config2 = models.BuildConfig.objects.exclude(pk=job.config.pk).first()
    url = reverse('ci:client:claim_job', args=[user.build_key, config2.name, 'testClient'])
    post_data = {'job_id': job_id}
    response = self.client_post_json(url, post_data)
    self.assertEqual(response.status_code, 400) # bad request

    # bad job
    url = reverse('ci:client:claim_job', args=[user.build_key, job.config.name, 'testClient'])
    post_data = {'job_id': 0}
    response = self.client_post_json(url, post_data)
    self.assertEqual(response.status_code, 400) # bad request


    # valid job, should be ok
    post_data = {'job_id': job_id}
    response = self.client_post_json(url, post_data)
    self.assertEqual(response.status_code, 200)

    data = json.loads(response.content)
    self.assertEqual(data['job_id'], job_id)
    self.assertEqual(data['status'], 'OK')

  def test_job_finished(self):
    user = utils.get_test_user()
    job = utils.create_job(user=user)
    client = utils.create_client()
    client2 = utils.create_client(name='other_client')
    job.client = client
    job.save()
    post_data = {'seconds': 0, 'complete': True}
    url = reverse('ci:client:job_finished', args=[user.build_key, client.name, job.pk])

    # only post allowed
    response = self.client.get(url)
    self.assertEqual(response.status_code, 405) # not allowed

    # bad url 
    url = reverse('ci:client:job_finished', args=[user.build_key, client.name, 0])
    response = self.client_post_json(url, post_data)
    self.assertEqual(response.status_code, 400) # bad request

    # unknown client
    url = reverse('ci:client:job_finished', args=[user.build_key, 'unknown_client', job.pk])
    response = self.client_post_json(url, post_data)
    self.assertEqual(response.status_code, 400) # bad request

    # bad client
    url = reverse('ci:client:job_finished', args=[user.build_key, client2.name, job.pk])
    response = self.client_post_json(url, post_data)
    self.assertEqual(response.status_code, 400) # bad request

    # should be ok
    url = reverse('ci:client:job_finished', args=[user.build_key, client.name, job.pk])
    response = self.client_post_json(url, post_data)
    self.assertEqual(response.status_code, 200)
    data = json.loads(response.content)
    self.assertIn('message', data)
    self.assertEqual(data['status'], 'OK')

    job2 = utils.create_job(event=job.event)
    job2.ready = False
    job2.complete = False
    job2.status = models.JobStatus.NOT_STARTED
    job2.active = True
    job2.save()
    # should be ok
    url = reverse('ci:client:job_finished', args=[user.build_key, client.name, job.pk])
    response = self.client_post_json(url, post_data)
    self.assertEqual(response.status_code, 200)
    data = json.loads(response.content)
    self.assertIn('message', data)
    self.assertEqual(data['status'], 'OK')
    job2 = models.Job.objects.get(pk=job2.pk)
    self.assertTrue(job2.ready)

  def test_step_complete_pr_status(self):
    user = utils.get_test_user()
    job = utils.create_job(user=user)
    job.status = models.JobStatus.CANCELED
    job.save()
    results = utils.create_step_result(job=job)
    results.exit_status = 1
    results.save()
    request = self.factory.get('/')
    views.step_complete_pr_status(request, results, job)

  def test_update_step_result(self):
    user = utils.get_test_user()
    job = utils.create_job(user=user)
    result = utils.create_step_result(job=job)
    client = utils.create_client()
    client2 = utils.create_client(name='other_client')
    job.client = client
    job.event.cause = models.Event.PULL_REQUEST
    job.save()

    post_data = {
        'step_id': result.step.pk,
        'step_num': result.step.position,
        'output': 'output',
        'time': 5,
        'complete': True,
        'exit_status': 0
        }
    url = reverse('ci:client:update_step_result', args=[user.build_key, client.name, result.pk])
    # only post allowed
    response = self.client.get(url)
    self.assertEqual(response.status_code, 405) # not allowed

    # bad step result
    url = reverse('ci:client:update_step_result', args=[user.build_key, client.name, 0])
    response = self.client_post_json(url, post_data)
    self.assertEqual(response.status_code, 400) # bad request

    # unknown client
    url = reverse('ci:client:update_step_result', args=[user.build_key, 'unknown_client', result.pk])
    response = self.client_post_json(url, post_data)
    self.assertEqual(response.status_code, 400) # bad request

    # bad client
    url = reverse('ci:client:update_step_result', args=[user.build_key, client2.name, result.pk])
    response = self.client_post_json(url, post_data)
    self.assertEqual(response.status_code, 400) # bad request

    # ok
    url = reverse('ci:client:update_step_result', args=[user.build_key, client.name, result.pk])
    response = self.client_post_json(url, post_data)
    self.assertEqual(response.status_code, 200) # bad request
    result = models.StepResult.objects.get(pk=result.pk)
    self.assertEqual(result.status, models.JobStatus.SUCCESS)

    url = reverse('ci:client:update_step_result', args=[user.build_key, client.name, result.pk])
    post_data['exit_status'] = 1
    response = self.client_post_json(url, post_data)
    self.assertEqual(response.status_code, 200) # bad request
    result = models.StepResult.objects.get(pk=result.pk)
    self.assertEqual(result.status, models.JobStatus.FAILED)

    url = reverse('ci:client:update_step_result', args=[user.build_key, client.name, result.pk])
    job = models.Job.objects.get(pk=job.pk)
    job.status = models.JobStatus.CANCELED
    job.save()
    response = self.client_post_json(url, post_data)
    self.assertEqual(response.status_code, 200) # bad request
