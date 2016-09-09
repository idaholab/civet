# CIVET
Continuous Integration, Verification, Enhancement, and Testing

[Moosebuild](https://www.moosebuild.org) written in Django.

[![Build status](https://www.moosebuild.org/44/status.svg)](https://www.moosebuild.org/repo/19/)

### Adding recipes

Civet now relies on a separate Git repository to store all recipe information.
Recipes are in python ConfigParser format.
See [INL civet_recipes](https://github.com/idaholab/civet_recipes) for examples.
The general procedure is the following:

1. Fork github.com:idaholab/civet_recipes
2. Clone your fork:  
    `git clone git@github.com:<username>/civet_recipes`
3. Create a feature branch off of devel  
    `git checkout devel`  
    `git checkout -b feature_branch`  
4. Make changes and commit and push back up to Github.  
    `git commit -a -m"Git commit message"`  
    `git push origin feature_branch`  
5. Submit a pull request against idaholab/civet_recipes `devel` branch. This will
initiate testing and make sure your changes are valid. Someone will need to review
and merge your pull request before it will be active.

Two of the most important parts of the recipe file are:
* `build_user`: The user that this recipe will be attached to.
Jobs created from this recipe can only be run with clients that know the build key assigned to this user.
For example, if you put your username here then the INL clients will **NOT** run these recipes and you will
have to run your own client.
* `repository`: The repository that the Civet server will receive events for. This can be any repository on any
supported Git server (GitHub, GitLab, BitBucket) that we can receive events for. 

### Running your own client

The client requires the `requests` and `DaemonLite` python modules to run. Install them via `pip` or
whatever installation method you prefer.


There are two main pieces of information you need to run your own client.

1. Server URL: For example https://www.moosebuild.org
2. Build key: This is generated for you when you first sign in to Civet and will
be displayed on the "recipes" page. This should not be shared.

#### Basic client

The basic client is `client/client.py`. It is intended to run via command line or cron. All
parameters are put on the command line. You will also need to set and export the `BUILD_ROOT`
environment variable to where you want all testing done.  
Other useful environment variables include:  
* `MOOSE_JOBS` : Will cause `make` and `run_tests` to use `-j $MOOSE_JOBS`
* `MAKE_JOBS` : Will cause `make` to use `-j $MAKE_JOBS`. Overrides `MOOSE_JOBS`
* `MAX_MAKE_LOAD` : Will cause `make` to use `-j $MAKE_JOBS -l $MAX_MAKE_LOAD`
* `TEST_JOBS` : Will cause `run_tests` to use `-j $TEST_JOBS`. Overrides `MOOSE_JOBS`
* `MAX_TEST_LOAD` : Will cause `run_tests` to use `-j $TEST_JOBS -l $MAX_TEST_LOAD`

An example command line might be (executed in the `client` directory):  
`./client.py --url https://www.moosebuild.org --build-key <Your assigned key> --configs linux-gnu --name <username>_client --insecure`

#### INL client

The INL client is in `client/inl_client.py` and is what is used internally at INL. It runs as a daemon and has the ability
to load different modules based on the build config. It can also poll more than one Civet
server. At the top of `client/inl_client.py` is where you configure the servers ( and the associated build keys ) as well
as what modules are loaded on a particular build config.

`BUILD_ROOT` and `MOOSE_JOBS` environment variables are set automatically but you can still export
`MAKE_JOBS`, `MAX_MAKE_LOAD`, `TEST_JOBS`, and `MAX_TEST_LOAD`.

To start the client, an example command might be:  
`./inl_client.py --num-jobs 12 --client 0 --daemon start`

To quit the client, an example command might be:  
`./inl_client.py --num-jobs 12 --client 0 --daemon stop`

### Setting up private client with moosebuild.org

In this scenario you want to run your own client to test a repository but you
want the results to be hosted on [moosebuild](https://www.moosebuild.org).
You will first need to create recipes that will be activated for your
repository that you are interested in testing. See the "Adding recipes" section above.
In each of the recipes you will need to set `build_user` to your username and `repository`
to the full git path of the repository. For example `git@github.com:username/new_repo`.

##### Webhook

We try to automatically install the correct webhook on your repository to notify moosebuild when an event occurs.
If we don't have access to do that on your repository then you will need to install a webhook
manually on your repository. Go to your repository on GitHub and then to `Settings->Webhooks & services->Add webhook`.

Payload URL: https://www.moosebuild.org/github/webhook/YOUR_BUILD_KEY/  
Content type: application/json  
Secret: blank  
Keep SSL verifcation disabled.  
Events: Pull request, Push  

Once that is enabled moosebuild.org will receive pull request and push events and setup the appropiate jobs to be run
by your client.
Then you should be able to run your own client, see "Running your own client" above.

### Server Installation

See `civet/settings.py` for required settings. Namely, setting the client_id/secret (if required) for the server to allow
Civet to generate access tokens for users.

Setup the database:

    ./manage.py makemigrations
    ./manage.py migrate
    ./manage.py createsupseruser

For public moosebuild.org:

    ./manage.py loaddata public.json

For internal:

    ./manage.py loaddata internal.json


### License

Copyright 2016 Battelle Energy Alliance, LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
