Installation
============

We recommend running using the Docker/OCI image; this contains all of the
necessary dependencies and static file handling preconfigured for you.

All configuration is done via either environment variables, or online through
the web interface.


Prerequisites
-------------

* SSL support (Takahē *requires* HTTPS)
* Something that can run Docker/OCI images
* A PostgreSQL 14 (or above) database
* Hosting/reverse proxy that passes the ``HOST`` header down to Takahē
* One of these to store uploaded images and media:

  * Amazon S3
  * Google Cloud Storage
  * Writable local directory (must be accessible by all running copies!)

Note that ActivityPub is a chatty protocol that has a lot of background
activity, so you will need to run *background tasks*, in
order to fetch profiles, retry delivery of posts, and more.

Ideally, you would choose a platform where you can run our worker process in
the background continuously, but for small installations we have a URL you can
call periodically instead - see "What To Run", below.

The flagship Takahē instance, `takahe.social <https://takahe.social>`_, runs
inside of Kubernetes, with one Deployment for the webserver and one for the
Stator runner.


What To Run
-----------

You need to run at least one copy of the
`Docker image <https://hub.docker.com/r/jointakahe/takahe>`_ with no extra
arguments, in order to serve web traffic.

The image has required environment variables before it will boot, and this is
the only way to configure it - see below.

You also need to ensure Stator, our background task system, runs regularly.
You can do this in one of two ways:

* Run another copy of image with the arguments ``python manage.py runstator``,
  which will run a background worker continuously.

* Call the URL ``/.stator/?token=abc`` periodically (once a minute or more).
  The token value must be the same as you set in ``TAKAHE_STATOR_TOKEN``.

The background worker will have a lot more throughput, but you can opt for
either for a small installation. If Stator gets backed up, you can either
run more workers or call the URL more often to ensure it gets more throughput.

While you can run Takahē directly from a checkout if you like (rather than
having to use the Docker image), we're not
officially supporting that right now, as it increases our support burden by
having to deal with lots of OS and library versions. It's a standard Django
app, though, so if you know what you're doing, have at it - just expect us to
push back if you file tickets about things not working on your OS!


Environment Variables
---------------------

All of these variables are *required* for a working installation, and should
be provided from the first boot.

* ``TAKAHE_DATABASE_SERVER`` should be a database DSN for your database (you can use
  the standard ``PGHOST``, ``PGUSER``, etc. variables instead if you want)

* ``TAKAHE_SECRET_KEY`` must be a fixed, random value (it's used for internal
  cryptography). Don't change this unless you want to invalidate all sessions.

* ``TAKAHE_MEDIA_BACKEND`` must be a URI starting with ``local://``, ``s3://`` or ``gcs://``.

  * If it is set to ``local://``, you must also provide ``TAKAHE_MEDIA_ROOT``,
    the path to the local media directory, and ``TAKAHE_MEDIA_URL``, a
    fully-qualified URL prefix that serves that directory.

  * If it is set to ``gcs://``, it must be in the form ``gcs://bucket-name``
    (note the two slashes if you just want a bucket name)

  * If it is set to ``s3://``, it must be in the form ``s3://access-key:secret-key@endpoint-url/bucket-name``

* ``TAKAHE_MAIN_DOMAIN`` should be the domain name (without ``https://``) that
  will be used for default links (such as in emails). It does *not* need to be
  the same as any domain you are hosting user accounts on.

* ``TAKAHE_EMAIL_SERVER`` should be set to an ``smtp://`` or ``sendgrid://`` URI

  * If you are using SMTP, it is ``smtp://username:password@host:port/``. You
    can also put ``?tls=true`` or ``?ssl=true`` on the end to enable encryption.

  * If you are using SendGrid, you should set the URI to ``sendgrid://api-key``

* ``TAKAHE_EMAIL_FROM`` is the email address that emails from the system will
  appear to come from.

* ``TAKAHE_AUTO_ADMIN_EMAIL`` should be an email address that you would like to
  be automatically promoted to administrator when it signs up. You only need
  this for initial setup, and can unset it after that if you like.

* If you don't want to run Stator as a background process but as a view,
  set ``TAKAHE_STATOR_TOKEN`` to a random string that you are using to
  protect it; you'll use this when setting up the URL to be called.

* If your installation is behind a HTTPS endpoint that is proxying it, set
  ``TAKAHE_USE_PROXY_HEADERS`` to ``true``. (The HTTPS proxy header must be called
  ``X-Forwarded-Proto``).

* If you want to receive emails about internal site errors, set
  ``TAKAHE_ERROR_EMAILS`` to a comma-separated list of email addresses that
  should get them.


Migrations
----------

You will have to run ``manage.py migrate`` when you first install Takahē in
order to create the database tables; how you do this is up to you. You can
shell into a running machine, create a one-off task that uses the Docker image,
or something else.

You will also have to run this for minor version releases when new migrations
are present; the release notes for each release will tell you if one is.


Making An Admin Account
-----------------------

Once the webserver is up and working, go to the "create account" flow and
create a new account using the email you specified in
``TAKAHE_AUTO_ADMIN_EMAIL``.

Once you set your password using the link emailed to you, you will have an
admin account.

If your email settings have a problem and you don't get the email, don't worry;
fix them and then follow the "reset my password" flow on the login screen, and
you'll get another password reset email that you can use.

If you have shell access to the Docker image and would rather use that, you
can run ``python3 manage.py createsuperuser`` instead and follow the prompts.


Adding A Domain
---------------

When you login you'll be greeted with the "make an identity" screen, but you
won't be able to as you will have no domains yet.

You should select the "Domains" link in the sidebar and create one, and then
you will be able to make your first identity.
