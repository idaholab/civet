# CIVET
Continuous Integration, Verification, Enhancement, and Testing

[Moosebuild](https://www.moosebuild.org) written in Django.

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

### Running your own client

There are two main pieces of information you need to run your own client.

1. Server URL: For example https://www.moosebuild.org
2. Build key: This is generated for you when you first sign in to Civet and will
be displayed on the "recipes" page. This should not be shared.

#### Basic client

The basic client is `client/client.py`. It is intended to run via command line or cron. All
parameters are put on the command line. Additionally it is generally a good idea to export
the BUILD_ROOT environment variable to where you want all testing done.

#### INL client

The INL client is in `client/inl_client.py` and is what is used internally at INL. It runs as a daemon and has the ability
to load different modules based on the build config. It can also poll more than one Civet
server. At the top of `client/inl_client.py` is where you configure the servers ( and the associated build keys ) as well
as what modules are loaded on a particular build config.

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
