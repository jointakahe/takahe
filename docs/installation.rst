Installation
============

We recommend running using the Docker/OCI image; this contains all of the
necessary dependencies and static file handling preconfigured for you.

All configuration is done via either environment variables, or online through
the web interface.


Prerequisites
-------------

* SSL support (Takahē *requires* HTTPS)
* Something that can run Docker/OCI images ("serverless" platforms are fine!)
* A PostgreSQL 14 (or above) database
* One of these to store uploaded images and media:
  * Amazon S3
  * Google Cloud Storage
  * Writable local directory (must be accessible by all running copies!)


Environment Variables
---------------------

All of these variables are *required* for a working installation, and should
be provided from the first boot.

* ``PGHOST``, ``PGPORT``, ``PGUSER``, ``PGDATABASE``, and ``PGPASSWORD`` are the
  standard PostgreSQL environment variables for configuring your database.

* ``TAKAHE_MEDIA_BACKEND`` must be one of ``local``, ``s3`` or ``gcs``.

    * If it is set to ``local``, you must also provide ``TAKAHE_MEDIA_ROOT``,
      the path to the local media directory, and ``TAKAHE_MEDIA_URL``, a
      fully-qualified URL prefix that serves that directory.

    * If it is set to ``gcs``, you must also provide ``TAKAHE_MEDIA_BUCKET``,
      the name of the bucket to store files in.

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
