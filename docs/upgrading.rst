Upgrading
=========

To upgrade Takahē you first need to pull the image by the tag name of the version
you would like to upgrade to. Do this first before stopping your running container
to reduce downtime waiting for the image to be downloaded.

If you are using yaml based provisioning systems like docker compose or similar
make sure you updated the pinned version like ``takahe:<version>`` (replacing
``<version>`` by the desired version you are upgrading to).

In case you are using tag name ``latest`` (e.g. ``takahe:latest``) just by pulling the
image should be enough to fetch the latest.

With the new image in your server you can now stop the running containers and spawn
new ones that will pick the version you defined.

.. warning::

  If you are not running a startup container to perform data migrations before
  starting the web server and the stator make sure you log into your container
  to perform a data migration with ``python3 manage.py migrate``.
