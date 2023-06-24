Releases
========

Versions
--------

.. toctree::
   :maxdepth: 1

   0.9
   0.8
   0.7
   0.6
   0.5
   0.4
   0.3


Versioning Policy
-----------------

Takahē approximately follows Semantic Versioning, with some specific
clarifications about what each upgrade means to you as a server administrator:

* **Patch** releases are bugfixes or small feature improvements that do not
  require a database migration. It is safe to run patch versions from the same
  minor series at the same time during an upgrade.

* **Minor** releases are larger feature improvements or other changes that
  require a database migration. Unless otherwise noted, these will be
  backwards-compatible migrations that can be applied to the database while the
  previous version is still running, before the running code is updated.

* **Major** releases may have major breaking changes that require significant
  upgrade time to perform, and will likely incur downtime. The exception will
  be our 1.0 release, which will be treated as a minor release, continuing
  on from the 0.x release series.

All release and upgrade notes can be found here, in the documentation.
