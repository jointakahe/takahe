Installation
============

We've tried to make installing and running Takahē as easy as possible, but
an ActivityPub server does have a minimum level of complexity, so you should
be experienced deploying software in order to run it.

Note that getting the technology running is arguably the easiest piece of
running a server - you must also be prepared to support your users, moderate,
defederate, keep on top of security risks, and know how you will
handle illegal content.


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
activity, so you will need to run *background tasks*, in order to fetch
profiles, retry delivery of posts, and more - see "Preparation", below.

The flagship Takahē instance, `takahe.social <https://takahe.social>`_, runs
inside of Kubernetes, with one Deployment for the webserver and one for the
Stator runner.

All configuration is done via either environment variables, or online through
the web interface.


Preparation
-----------

You'll need to run two copies of our `Docker image <https://hub.docker.com/r/jointakahe/takahe>`_:

* One with no extra arguments (command), which will serve web traffic

* One with the arguments ``python3 manage.py runstator``, which will run the background worker

These containers will need the ability to write at least 1GB of files out
to their scratch disks. See the ``TAKAHE_NGINX_CACHE_SIZE`` environment
variable for more.

.. note::

    If you cannot run a background worker for some reason, you can instead
    call the URL ``/.stator/?token=abc`` periodically (once a minute or more).
    The token value must be the same as you set in the ``TAKAHE_STATOR_TOKEN``
    environment variable. This pattern is only suitable for very small installs.

While it is possible to install and run Takahē directly from a directory,
rather than the Docker image, we don't provide support for that method due to
the difficulty of getting libraries to all match. Takahē is a standard Django
project, so if you know what you're doing, go for it - but we won't be able
to give you support.

If you are running on Kubernetes, we recommend that you make one Deployment
for the webserver and one Deployment for the background worker. We also
recommend that you mount an ``emptyDir`` to the ``/cache/`` path on the
webserver containers, as this is where the media cache will be stored.


Environment Variables
---------------------

All of these variables are *required* for a working installation, and should
be provided to the containers from the first boot.

* ``TAKAHE_DATABASE_SERVER`` should be a database DSN for your database (you can use
  the standard ``PGHOST``, ``PGUSER``, etc. variables instead if you want)

* ``TAKAHE_SECRET_KEY`` must be a fixed, random value (it's used for internal
  cryptography). Don't change this unless you want to invalidate all sessions.

  .. warning::

    You **must** keep the value of ``TAKAHE_SECRET_KEY`` unique and secret. Anyone
    with this value can modify their session to impersonate any user, including
    admins. It should be kept even more secure than your admin passwords, and
    should be long, random and completely unguessable. We recommend that it is
    at least 64 characters.

* ``TAKAHE_MEDIA_BACKEND`` must be a URI starting with ``local://``, ``s3://``
  or ``gcs://``. See :ref:`media_configuration` below for more.


* ``TAKAHE_MAIN_DOMAIN`` should be the domain name (without ``https://``) that
  will be used for default links (such as in emails). It does *not* need to be
  the same as any domain you are hosting user accounts on.

* ``TAKAHE_EMAIL_SERVER`` should be set to an ``smtp://`` or ``sendgrid://`` URI.
  See :ref:`email_configuration` below for more.

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
  ``TAKAHE_ERROR_EMAILS`` to a valid JSON list of emails, such as
  ``["andrew@aeracode.org"]`` (if you're doing this via shell, be careful
  about escaping!)

There are some other, optional variables you can tweak once the
system is up and working - see :doc:`tuning` for more.

If you are behind a caching proxy, such as Cloudflare, you may need to update
your CSRF host settings to match. Takahē validates that requests have an
Origin header that matches their Referer header by default, and these services
can break that relationship.

Takahē lets you set this up via the ``TAKAHE_CSRF_HOSTS`` environment variable, which takes
a Python-list-formatted list of additional protocols/domains to allow, with wildcards. It feeds
directly into Django's `CSRF_TRUSTED_ORIGINS <https://docs.djangoproject.com/en/4.2/ref/settings/#csrf-trusted-origins>`_
setting, so for more information about how to use it, see `the Django documentation <https://docs.djangoproject.com/en/4.2/ref/settings/#csrf-trusted-origins>`_ - generally, you'd want to set it to
your website's public address, so for our server it would have been
``TAKAHE_CSRF_HOSTS='["https://takahe.social"]'``.


.. _media_configuration:

Media Configuration
~~~~~~~~~~~~~~~~~~~

Takahē needs somewhere to store uploaded post attachments, profile images
and more ("media"). We support Amazon S3, Google Cloud Storage and a local
directory, but we recommend against the local directory unless you know what
you're doing - media must be accessible from every running container in a
read-write mode, and this is hard to do with a directory as you scale.

Support for CDN configuration for media is coming soon.


Amazon S3
#########

To use S3, provide a URL in one of these forms:

* ``s3:///bucket-name``
* ``s3://endpoint-url/bucket-name``
* ``s3://access-key:secret-key@endpoint-url/bucket-name``

If you omit the keys or the endpoint URL, then Takahē will try to use implicit
authentication for them. The keys, if included, should be urlencoded, as AWS
secret keys commonly contain eg + characters.

Your S3 bucket *must* be set to allow publically-readable files, as Takahē will
set all files it uploads to be ``public-read``. We randomise uploaded file
names to prevent enumeration attacks.


Google Cloud Storage
####################

To use GCS, provide a URL like:

* ``gs:///bucket-name``

The GCS backend currently only supports implicit authentication (from the
standard Google authentication environment variables, or machine roles).

Your bucket must be set to world-readable and have individual object
permissions disabled.


Local Directory
###############

To use a local directory, specify the media URL as ``local://``.

You must then also specify:

* ``TAKAHE_MEDIA_ROOT``, the file path to the local media Directory
* ``TAKAHE_MEDIA_URL``, a fully-qualified URL prefix that serves that directory (must end in a slash)

The media directory must be read-write accessible from every single container
of Takahē - webserver and workers alike.


.. _email_configuration:

Email Configuration
~~~~~~~~~~~~~~~~~~~

Takahē requires an email server in order to send password reset and other
account emails. We support either explicit SMTP, or auto-configuration of SMTP
for SendGrid.

SMTP
####

Provide a URL in the form ``smtp://username:password@host:port/``

If you are using TLS, add ``?tls=true`` to the end. If you are using
SSL, add ``?ssl=true`` to the end.

If your username and password have URL-unsafe characters in them, you can
URLencode them. For example, if I had to use the username ``someone@example.com``
with the password ``my:password``, it would be represented as::

  smtp://someone%40example.com:my%3Apassword@smtp.example.com:25/

The username and password can be omitted, with a URL in the form
``smtp://host:port/``, if your mail server is a (properly firewalled!)
unauthenticated relay.

SendGrid
########

If you are using SendGrid, Takahē will auto-configure the SMTP settings for you.
Simply set the email server to ``sendgrid://api-key``.


Database
--------

Takahē requires a PostgreSQL database at version 14 or above in order to work
properly. You should create a database within your PostgreSQL server, with its
own username and password, and provide Takahē with those credentials via
``TAKAHE_DATABASE_SERVER`` (see above). It will make its own tables and indexes.

You will have to run ``python3 manage.py migrate`` when you first install Takahē in
order to create the database tables; how you do this is up to you.
We recommend one of:

* Shell/Exec into a running container (such as the webserver) and run it there.

* Launch a separate container as a one-off with ``python3 manage.py migrate`` as its arguments/command. If you are using Kubernetes, you should use a Job (or a one-off Pod) for this rather than a Deployment

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


Tuning and Scaling
------------------

See :doc:`/tuning` for all the things you should tweak as your server gains
users. We recommend setting up caches early on!
