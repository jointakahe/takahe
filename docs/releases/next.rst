

Upgrade Notes
-------------

VAPID keys and Push notifications
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Takahē now supports push notifications if you supply a valid VAPID keypair as
the ``TAKAHE_VAPID_PUBLIC_KEY`` and ``TAKAHE_VAPID_PRIVATE_KEY`` environment
variables. You can generate a keypair via `https://web-push-codelab.glitch.me/`_.

Note that users of apps may need to sign out and in again to their accounts for
the app to notice that it can now do push notifications. Some apps, like Elk,
may cache the fact your server didn't support it for a while.


Marker Support
~~~~~~~~~~~~~~

Takahē now supports the `Markers API <https://docs.joinmastodon.org/methods/markers/>`_,
used by clients to sync read positions within timelines.


Lists Support
~~~~~~~~~~~~~

Takahē now supports the `Lists APIs <https://docs.joinmastodon.org/methods/lists/>`_,
used by clients to maintain lists of accounts to show timelines for.
