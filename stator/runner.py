import datetime
import os
import signal
import time
import traceback
import uuid
from concurrent.futures import Future, ThreadPoolExecutor

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from core import exceptions, sentry
from core.models import Config
from stator.models import StatorModel, Stats


class LoopingTimer:
    """
    Triggers check() to be true once every `interval`.
    """

    next_run: float | None = None

    def __init__(self, interval: float, trigger_at_start=True):
        self.interval = interval
        self.trigger_at_start = trigger_at_start

    def check(self) -> bool:
        # See if it's our first time being called
        if self.next_run is None:
            # Set up the next call based on trigger_at_start
            if self.trigger_at_start:
                self.next_run = time.monotonic()
            else:
                self.next_run = time.monotonic() + self.interval
        # See if it's time to run the next call
        if time.monotonic() >= self.next_run:
            self.next_run = time.monotonic() + self.interval
            return True
        return False


class StatorRunner:
    """
    Runs tasks on models that are looking for state changes.
    Designed to run either indefinitely, or just for a few seconds.
    """

    def __init__(
        self,
        models: list[type[StatorModel]],
        concurrency: int = getattr(settings, "STATOR_CONCURRENCY", 30),
        concurrency_per_model: int = getattr(
            settings, "STATOR_CONCURRENCY_PER_MODEL", 15
        ),
        liveness_file: str | None = None,
        schedule_interval: int = 60,
        delete_interval: int = 30,
        lock_expiry: int = 300,
        run_for: int = 0,
    ):
        self.models = models
        self.runner_id = uuid.uuid4().hex
        self.concurrency = concurrency
        self.concurrency_per_model = concurrency_per_model
        self.liveness_file = liveness_file
        self.schedule_interval = schedule_interval
        self.delete_interval = delete_interval
        self.lock_expiry = lock_expiry
        self.run_for = run_for
        self.minimum_loop_delay = 0.5
        self.maximum_loop_delay = 5
        self.tasks: list[Future] = []
        # Set up SIGALRM handler
        signal.signal(signal.SIGALRM, self.alarm_handler)

    def run(self):
        sentry.set_takahe_app("stator")
        self.handled = {}
        self.started = time.monotonic()
        self.executor = ThreadPoolExecutor(max_workers=self.concurrency)
        self.loop_delay = self.minimum_loop_delay
        self.scheduling_timer = LoopingTimer(self.schedule_interval)
        self.deletion_timer = LoopingTimer(self.delete_interval)
        # For the first time period, launch tasks
        print("Running main task loop")
        try:
            with sentry.configure_scope() as scope:
                while True:
                    # See if we need to run cleaning
                    if self.scheduling_timer.check():
                        # Set up the watchdog timer (each time we do this the previous one is cancelled)
                        signal.alarm(self.schedule_interval * 2)
                        # Write liveness file if configured
                        if self.liveness_file:
                            with open(self.liveness_file, "w") as fh:
                                fh.write(str(int(time.time())))
                        # Refresh the config
                        self.load_config()
                        # Do scheduling (stale lock deletion and stats gathering)
                        self.run_scheduling()

                    # Clear the cleaning breadcrumbs/extra for the main part of the loop
                    sentry.scope_clear(scope)

                    self.clean_tasks()

                    # See if we need to add deletion tasks
                    if self.deletion_timer.check():
                        self.add_deletion_tasks()

                    # Fetch and run any new handlers we can fit
                    self.add_transition_tasks()

                    # Are we in limited run mode?
                    if (
                        self.run_for
                        and (time.monotonic() - self.started) > self.run_for
                    ):
                        break

                    # Prevent busylooping, but also back off delay if we have
                    # no tasks
                    if self.tasks:
                        self.loop_delay = self.minimum_loop_delay
                    else:
                        self.loop_delay = min(
                            self.loop_delay * 1.5,
                            self.maximum_loop_delay,
                        )
                    time.sleep(self.loop_delay)

                    # Clear the Sentry breadcrumbs and extra for next loop
                    sentry.scope_clear(scope)
        except KeyboardInterrupt:
            pass

        # Wait for tasks to finish
        print("Waiting for tasks to complete")
        self.executor.shutdown()

        # We're done
        print("Complete")

    def alarm_handler(self, signum, frame):
        """
        Called when SIGALRM fires, which means we missed a schedule loop.
        Just exit as we're likely deadlocked.
        """
        print("Watchdog timeout exceeded")
        os._exit(2)

    def load_config(self):
        """
        Refreshes config from the DB
        """
        Config.system = Config.load_system()

    def run_scheduling(self):
        """
        Deletes stale locks for models, and submits their stats.
        """
        with sentry.start_transaction(op="task", name="stator.run_scheduling"):
            for model in self.models:
                print(
                    f"{model._meta.label_lower}: Scheduling ({self.handled.get(model._meta.label_lower, 0)} handled)"
                )
                self.submit_stats(model)
                model.transition_clean_locks()

    def submit_stats(self, model: type[StatorModel]):
        """
        Pop some statistics into the database from our local info for the given model
        """
        stats_instance = Stats.get_for_model(model)
        if stats_instance.model_label in self.handled:
            stats_instance.add_handled(self.handled[stats_instance.model_label])
            del self.handled[stats_instance.model_label]
        stats_instance.set_queued(model.transition_ready_count())
        stats_instance.trim_data()
        stats_instance.save()

    def add_transition_tasks(self, call_inline=False):
        """
        Adds a transition thread for as many instances as we can, given capacity
        and batch size limits.
        """
        # Calculate space left for tasks
        space_remaining = self.concurrency - len(self.tasks)
        # Fetch new tasks
        for model in self.models:
            if space_remaining > 0:
                for instance in model.transition_get_with_lock(
                    number=min(space_remaining, self.concurrency_per_model),
                    lock_expiry=(
                        timezone.now() + datetime.timedelta(seconds=self.lock_expiry)
                    ),
                ):
                    if call_inline:
                        task_transition(instance, in_thread=False)
                    else:
                        self.tasks.append(
                            self.executor.submit(task_transition, instance)
                        )
                    self.handled[model._meta.label_lower] = (
                        self.handled.get(model._meta.label_lower, 0) + 1
                    )
                    space_remaining -= 1

    def add_deletion_tasks(self, call_inline=False):
        """
        Adds a deletion thread for each model
        """
        # Yes, this potentially goes over the capacity limit - it's fine.
        for model in self.models:
            if model.state_graph.deletion_states:
                if call_inline:
                    task_deletion(model, in_thread=False)
                else:
                    self.tasks.append(self.executor.submit(task_deletion, model))

    def clean_tasks(self):
        """
        Removes any tasks that are done and handles exceptions if they
        raised them.
        """
        new_tasks = []
        for task in self.tasks:
            if task.done():
                try:
                    task.result()
                except BaseException as e:
                    exceptions.capture_exception(e)
                    traceback.print_exc()
            else:
                new_tasks.append(task)
        self.tasks = new_tasks

    def run_single_cycle(self):
        """
        Testing entrypoint to advance things just one cycle, and allow errors
        to propagate out.
        """
        self.add_deletion_tasks(call_inline=True)
        self.add_transition_tasks(call_inline=True)


def task_transition(instance: StatorModel, in_thread: bool = True):
    """
    Runs one state transition/action.
    """
    task_name = f"stator.task_transition:{instance._meta.label_lower}#{{id}} from {instance.state}"
    started = time.monotonic()
    with sentry.start_transaction(op="task", name=task_name):
        sentry.set_context(
            "instance",
            {
                "model": instance._meta.label_lower,
                "pk": instance.pk,
                "state": instance.state,
                "state_age": instance.state_age,
            },
        )
        result = instance.transition_attempt()
        duration = time.monotonic() - started
        if result:
            print(
                f"{instance._meta.label_lower}: {instance.pk}: {instance.state} -> {result} ({duration:.2f}s)"
            )
        else:
            print(
                f"{instance._meta.label_lower}: {instance.pk}: {instance.state} unchanged  ({duration:.2f}s)"
            )
    if in_thread:
        close_old_connections()


def task_deletion(model: type[StatorModel], in_thread: bool = True):
    """
    Runs one model deletion set.
    """
    # Loop, running deletions every second, until there are no more to do
    while True:
        deleted = model.transition_delete_due()
        if not deleted:
            break
        print(f"{model._meta.label_lower}: Deleted {deleted} stale items")
        time.sleep(1)
    if in_thread:
        close_old_connections()
