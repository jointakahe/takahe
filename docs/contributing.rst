Contributing
============

Takahē, as an open source project, could always do with more help, and if you
want to contribute we'd love help in the following areas:

* Backend code development (Python)
* Frontend code development (HTML, CSS and very limited JavaScript)
* Visual design & UX (for our default UI, and the project site)
* Illustration (for the app, project site, and outreach materials)
* Writing (for our development and user documentation)

If you're interested in helping out, join `our Discord server <https://discord.gg/qvQ39tAMvf>`_`
or email contact@jointakahe.org, and mention what you'd like to help with.

All contributors are expected to abide by our `Code of Conduct <https://jointakahe.org/conduct/>`_.
We have zero tolerance for bigotry or discrimination.

If you feel like someone is breaking the code of conduct, or is making you feel
unwelcome in a way not explicitly outlined in it, you can email us at
conduct@jointakahe.com.


Running Locally
---------------

If you wish to run Takahē locally, these instructions will help you do that.
It is worth noting, however, that this will only really let you test the UI
and local posting/follow functionality; to test ActivityPub itself and follow
other people, your installation **must be accessible from the internet**;
doing that securely is different enough per person that it is not covered here.


Direct installation
~~~~~~~~~~~~~~~~~~~

Takahē requires Python 3.10 or above, so you'll need that first. Clone the repo::

    git clone https://github.com/jointakahe/takahe/

Then, ``cd`` into that directory and create and activate a virtual environment
(you can use other options, but this is the basic example)::

    python3 -m venv .venv
    . .venv/bin/activate

Then install the development requirements::

    pip install -r requirements-dev.txt

and enable the git commit hooks to do auto-formatting and linting
(if you don't do this, our CI system will reject your PRs until they match)::

    pre-commit install

You will need to set up some development settings (you can edit `.env` later)::

    cp development.env .env

You can run the web interface to see it at http://localhost:8000::

    ./manage.py runserver

You will need to run Stator in order to have background actions work::

    ./manage.py runstator

Make yourself a superuser account in order to log in:

    ./manage.py createsuperuser

And you can run the tests with pytest::

    pytest


Docker
~~~~~~

The docker build process will take care of much of the above, but you just have
to be sure that you're executing it from the project root.

First, you need to build your image::

    docker compose -f docker/docker-compose.yml build

Then start the `compose` session::

    docker compose -f docker/docker-compose.yml up

At this point, you will be able to see the Web UI at http://localhost:8000

Once your session is up and running, you can make yourself a superuser account::

    docker compose -f docker/docker-compose.yml exec web manage.py createsuperuser

And you can run the tests inside your container::

    docker compose -f docker/docker-compose.yml exec web pytest
    

Coding Guidelines
-----------------

We have linters, typechecking and formatters enabled for the project; ensure these
are set up locally by running `pre-commit install`, otherwise your pull request
will fail its testing phase.

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
