Contributing
============

Takahē, as an open source project, could always do with more help, and if you
want to contribute we'd love help in the following areas:

* Backend code development (Python)
* Frontend code development (HTML, CSS and very limited JavaScript)
* Visual design & UX (for our default UI, and the project site)
* Illustration (for the app, project site, and outreach materials)
* Writing (for our development and user documentation)
* Moderation (relayed advice and guidelines from those who have done it for Mastodon or others)
* Compliance, Trust & Safety (professional advice and guidelines on what servers will require)
* Other ActivityPub Servers (to help debug federation issues)

If you're interested in helping out, join `our Discord server <https://discord.gg/qvQ39tAMvf>`_
or email contact@jointakahe.org, and mention what you'd like to help with.

All contributors are expected to abide by our `Code of Conduct <https://jointakahe.org/conduct/>`_.
We have zero tolerance for bigotry or discrimination.

If you feel like someone is breaking the code of conduct, or is making you feel
unwelcome in a way not explicitly outlined in it, you can email us at
conduct@jointakahe.org.


Running Locally
---------------

If you wish to run Takahē locally, these instructions will help you do that.
It is worth noting, however, that this will only really let you test the UI
and local posting/follow functionality; to test ActivityPub itself and follow
other people, your installation **must be accessible from the internet**;
doing that securely is different enough per person that it is not covered here.

Using Docker Compose is the fastest way to get up and running, and you will
still be able to make web changes and have them appear in real-time. Direct
installation is recommended for more advanced developers or those wishing to
use a PostgreSQL they already have.

These instructions are not suitable for running a production copy; for that,
see :doc:`installation`.

Docker
~~~~~~

The docker build process will take care of much of the above, but you just have
to be sure that you're executing it from the project root.

First, you need to build your image::

    docker compose -f docker/docker-compose.yml build

Then start the ``compose`` session::

    docker compose -f docker/docker-compose.yml up

At this point, you should be able to see the Web UI at http://localhost:8000

Once your session is up and running, you can:

…make yourself a superuser account::

    docker compose -f docker/docker-compose.yml exec web python3 manage.py createsuperuser

…install the test dependencies inside your container::

    docker compose -f docker/docker-compose.yml exec web pip install -r requirements-dev.txt

…run the tests inside your container::

    docker compose -f docker/docker-compose.yml exec web pytest

If you want to change the settings that Takahē is using, you can edit them
near the top of the docker-compose file; the default set are designed for a
local installation, though.


Direct Installation
~~~~~~~~~~~~~~~~~~~

Takahē requires Python 3.10 or above, so you'll need that first. Clone the repo::

    git clone https://github.com/jointakahe/takahe/

The repo comes with a ``Makefile`` that simplifies some of the local development setup:

*Note: The default* ``make`` *targets use the postgres container from the Docker setup, so once built the db and migrations are already done. See below for instructions on setting up a local PostgreSQL instance for development.*

Setup the local python and git environment::

    make setup_local

Start the postgres db in Docker::

    make startdb

.. _start-web:

You can run the web interface to see it at http://localhost:8000::

    make runserver

You will need to run Stator in order to have background actions work::

    make runstator

Make yourself a superuser account in order to log in::

    make createsuperuser

And you can run the tests with pytest::

    make test

If you want to edit settings, you can edit the ``.env`` file.

Local PostgreSQL Setup
^^^^^^^^^^^^^^^^^^^^^^

Create a database in your local PostgreSQL instance::

    sudo -u postgres createdb takahe

Update the ``.env`` file produced by ``make setup_local`` to comment out the Docker-based ``TAKAHE_DATABASE_SERVER`` setting, and uncomment the other one (see the comments in the ``.env`` file).

Now you can apply migrations::

    . .venv/bin/activate
    python3 -m manage migrate

With the database connection changed, `the rest <#start-web>`_ of the Direct Installation instructions are the same.

Building Documentation
----------------------

We are using `Sphinx <https://www.sphinx-doc.org/en/master/index.html>`_ and `reStructuredText markup language <https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html>`_ to write documentation.

To build documentation, we need to install additional libraries::

    pip install -r docs/requirements.txt

After editing documentation, you can build documentation with the following command::

    make docs

This outputs HTML files under the ``docs/_build/html/`` directory. Let's launch a development server to serve HTML files::

    python -m http.server 8000 --directory docs/_build/html/

Now, you can view the documentation on your browser at http://localhost:8000/.


Coding Guidelines
-----------------

We have linters, typechecking and formatters enabled for the project; ensure these
are set up locally by running `python3 -m pre_commit install`, otherwise your pull
request will fail its testing phase.

Comment anything weird, unusual or complicated; if in doubt, leave a comment.

Don't use overly complex language constructs - like double-nested list comprehensions -
when a simple, understandable version is possible instead. We optimise for code
readability.

All features should be accessible without JavaScript if at all possible; this doesn't
mean that we can't have nice JavaScript user interfaces and affordances, but all
basic functionality *should* be accessible without it.

We use `HTMX <https://htmx.org/>`_ for dynamically loading content, and
`Hyperscript <https://hyperscript.org/>`_ for most interactions rather than raw
JavaScript. If you can accomplish what you need with these tools, please use them
rather than adding JS.
