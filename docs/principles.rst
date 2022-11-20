Design Principles
=================

Takahē is somewhat opinionated in its design goals, which are:

* Simplicity of maintenance and operation
* Multiple domain support
* Asychronous Python core
* Low-JS user interface

These are explained more below, but it's important to stress the one thing we
are not aiming for - scalability.

If we wanted to build a system that could handle hundreds of thousands of
accounts on a single server, it would be built very differently - queues
everywhere as the primary communication mechanism, most likely - but we're
not aiming for that.

Our final design goal is for around 10,000 users to work well, provided you do
some PostgreSQL optimisation. It's likely the design will work beyond that,
but we're not going to put any specific effort towards it.

After all, if you want to scale in a federated system, you can always launch
more servers. We'd rather work towards the ability to share moderation and
administration workloads across servers rather than have one giant big one.


Simplicity Of Maintenance
-------------------------

It's important that, when running a social networking server, you have as much
time to focus on moderation and looking after your users as you can, rather
than trying to be an SRE.

To this end, we use our deliberate design aim of "small to medium size" to try
and keep the infrastructure simple - one set of web servers, one set of task
runners, and a PostgreSQL database.

The task system (which we call Stator) is not based on a task queue, but on
a state machine per type of object - which have retry logic built in. The
system continually examines every object to see if it can progress its state
by performing an action, which is not quite as *efficient* as using a queue,
but recovers much more easily and doesn't get out of sync.


Multiple Domain Support
-----------------------

TODO


Asynchronous Python
-------------------

TODO


Low-JS User Interface
---------------------
