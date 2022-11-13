import os

from .base import *  # noqa

# Load secret key from environment
try:
    SECRET_KEY = os.environ["TAKAHE_SECRET_KEY"]
except KeyError:
    print("You must specify the TAKAHE_SECRET_KEY environment variable!")
    os._exit(1)

# Ensure debug features are off
DEBUG = False

# TODO: Allow better setting of allowed_hosts, if we need to
ALLOWED_HOSTS = ["*"]
