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
* One of these to store uploaded images and media:

  * Amazon S3
  * Google Cloud Storage
  * Writable local directory (must be accessible by all running copies!)

Note that ActivityPub is a chatty protocol that has a lot of background
activity, so you will need a platform that can run *background tasks*, in
order to fetch profiles, retry delivery of posts, and more.

This means that a "serverless" platform like AWS Lambda or Google Cloud Run is
not enough by itself; while you can use these to serve the web pages if you
like, you will need to run the Stator runner somewhere else as well.

The flagship Takahē instance, [takahe.social](https://takahe.social), runs
inside of Kubernetes, with one Deployment for the webserver and one for the
Stator runner.


What To Run
-----------

You need to run at least two copies of the Docker image:

* One with no command or arguments specified, which will serve web traffic
* One with the arguments (command) ``python manage.py runstator``, which will
  run the background worker that handles asynchronous communication with other
  servers.

Both of these can have as many copies run as needed. Note that the image has
required environment variables before it will boot, and this is the only way
to configure it - see below.


Environment Variables
---------------------

All of these variables are *required* for a working installation, and should
be provided from the first boot.

* ``PGHOST``, ``PGPORT``, ``PGUSER``, ``PGDATABASE``, and ``PGPASSWORD`` are the
  standard PostgreSQL environment variables for configuring your database.

* ``TAKAHE_SECRET_KEY`` must be a fixed, random value (it's used for internal
  cryptography). Don't change this unless you want to invalidate all sessions.

* ``TAKAHE_MEDIA_BACKEND`` must be one of ``local``, ``s3`` or ``gcs``.

    * If it is set to ``local``, you must also provide ``TAKAHE_MEDIA_ROOT``,
      the path to the local media directory, and ``TAKAHE_MEDIA_URL``, a
      fully-qualified URL prefix that serves that directory.

    * If it is set to ``gcs``, you must also provide ``TAKAHE_MEDIA_BUCKET``,
      the name of the bucket to store files in. The bucket must be publically
      readable and have "uniform access control" enabled.

    * If it is set to ``s3``, you must also provide ``TAKAHE_MEDIA_BUCKET``,
      the name of the bucket to store files in.

* ``TAKAHE_MAIN_DOMAIN`` should be the domain name (without ``https://``) that
  will be used for default links (such as in emails). It does *not* need to be
  the same as any domain you are hosting user accounts on.

* ``TAKAHE_EMAIL_HOST`` and ``TAKAHE_EMAIL_PORT`` (along with
  ``TAKAHE_EMAIL_USER`` and ``TAKAHE_EMAIL_PASSWORD``, if needed) should point
  to an SMTP server Takahe can use for sending email. Email is *required*, to
  allow account creation and password resets.

  * If you are using SendGrid, you can just set an API key in
    ``TAKAHE_EMAIL_SENDGRID_KEY`` instead.

* ``TAKAHE_EMAIL_FROM`` is the email address that emails from the system will
  appear to come from.

* ``TAKAHE_AUTO_ADMIN_EMAIL`` should be an email address that you would like to
  be automatically promoted to administrator when it signs up. You only need
  this for initial setup, and can unset it after that if you like.

* ``TAKAHE_STATOR_TOKEN`` should be a random string that you are using to
  protect the stator (task runner) endpoint. You'll use this value later.

* If your installation is behind a HTTPS endpoint that is proxying it, set
  ``TAKAHE_SECURE_HEADER`` to the header name used to signify that HTTPS is
  being used (usually ``X-Forwarded-Proto``)

* If you want to receive emails about internal site errors, set
  ``TAKAHE_ERROR_EMAILS`` to a comma-separated list of email addresses that
  should get them.


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
