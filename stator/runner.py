import asyncio
import datetime
import os
import signal
import time
import traceback
import uuid

from asgiref.sync import ThreadSensitiveContext, async_to_sync, sync_to_async
from django.conf import settings
from django.utils import timezone

from core import exceptions, sentry
from core.models import Config
from stator.models import StatorModel, Stats


class LoopingTask:
    """
    Wrapper for having a coroutine go in the background and only have one
    copy running at a time.
    """

    def __init__(self, callable):
        self.callable = callable
        self.task: asyncio.Task | None = None

    def run(self) -> bool:
        # If we have a task object, see if we can clear it up
        if self.task is not None:
            if self.task.done():
                self.task = None
            else:
                return False
        # OK, launch a new task
        self.task = asyncio.create_task(self.callable())
        return True


class StatorRunner:
    """
    Runs tasks on models that are looking for state changes.
    Designed to run either indefinitely, or just for a few seconds.
    """

    def __init__(
        self,
        models: list[type[StatorModel]],
        concurrency: int = getattr(settings, "STATOR_CONCURRENCY", 50),
        concurrency_per_model: int = getattr(
            settings, "STATOR_CONCURRENCY_PER_MODEL", 15
        ),
        liveness_file: str | None = None,
        schedule_interval: int = 30,
        lock_expiry: int = 300,
        run_for: int = 0,
    ):
        self.models = models
        self.runner_id = uuid.uuid4().hex
        self.concurrency = concurrency
        self.concurrency_per_model = concurrency_per_model
        self.liveness_file = liveness_file
        self.schedule_interval = schedule_interval
        self.lock_expiry = lock_expiry
        self.run_for = run_for
        self.minimum_loop_delay = 0.5
        self.maximum_loop_delay = 5
        # Set up SIGALRM handler
        signal.signal(signal.SIGALRM, self.alarm_handler)

    async def run(self):
        sentry.set_takahe_app("stator")
        self.handled = {}
        self.started = time.monotonic()
        self.last_clean = time.monotonic() - self.schedule_interval
        self.tasks = []
        self.loop_delay = self.minimum_loop_delay
        self.schedule_task = LoopingTask(self.run_scheduling)
        self.fetch_task = LoopingTask(self.fetch_and_process_tasks)
        self.config_task = LoopingTask(self.load_config)
        # For the first time period, launch tasks
        print("Running main task loop")
        try:
            with sentry.configure_scope() as scope:
                while True:
                    # Do we need to do cleaning?
                    if (time.monotonic() - self.last_clean) >= self.schedule_interval:
                        # Set up the watchdog timer (each time we do this the
                        # previous one is cancelled)
                        signal.alarm(self.schedule_interval * 2)
                        # Refresh the config
                        self.config_task.run()
                        if self.schedule_task.run():
                            print("Running cleaning and scheduling")
                        else:
                            print("Previous scheduling still running...!")
                        # Write liveness file if configured
                        if self.liveness_file:
                            with open(self.liveness_file, "w") as fh:
                                fh.write(str(int(time.time())))
                        self.last_clean = time.monotonic()

                    # Clear the cleaning breadcrumbs/extra for the main part of the loop
                    sentry.scope_clear(scope)

                    self.remove_completed_tasks()

                    # Fetching is kind of blocking, so we need to do this
                    # as a separate coroutine
                    self.fetch_task.run()

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
                    await asyncio.sleep(self.loop_delay)

                    # Clear the Sentry breadcrumbs and extra for next loop
                    sentry.scope_clear(scope)
        except KeyboardInterrupt:
            pass
        # Wait for tasks to finish
        print("Waiting for tasks to complete")
        while True:
            self.remove_completed_tasks()
            if not self.tasks:
                break
            # Prevent busylooping
            await asyncio.sleep(0.5)
        print("Complete")
        return self.handled

    def alarm_handler(self, signum, frame):
        """
        Called when SIGALRM fires, which means we missed a schedule loop.
        Just exit as we're likely deadlocked.
        """
        print("Watchdog timeout exceeded")
        os._exit(2)

    async def load_config(self):
        """
        Refreshes config from the DB
        """
        Config.system = await Config.aload_system()

    async def run_scheduling(self):
        """
        Do any transition cleanup tasks
        """
        if self.handled:
            print("Tasks processed since last flush:")
            for label, number in self.handled.items():
                print(f"  {label}: {number}")
        else:
            print("No tasks handled since last flush.")
        with sentry.start_transaction(op="task", name="stator.run_scheduling"):
            for model in self.models:
                await self.submit_stats(model)
                await model.atransition_clean_locks()
                await model.atransition_schedule_due()
                await model.atransition_delete_due()

    async def submit_stats(self, model):
        """
        Pop some statistics into the database
        """
        stats_instance = await Stats.aget_for_model(model)
        if stats_instance.model_label in self.handled:
            stats_instance.add_handled(self.handled[stats_instance.model_label])
            del self.handled[stats_instance.model_label]
        stats_instance.set_queued(await model.atransition_ready_count())
        stats_instance.trim_data()
        await sync_to_async(stats_instance.save)()

    async def fetch_and_process_tasks(self):
        # Calculate space left for tasks
        space_remaining = self.concurrency - len(self.tasks)
        # Fetch new tasks
        for model in self.models:
            if space_remaining > 0:
                for instance in await model.atransition_get_with_lock(
                    number=min(space_remaining, self.concurrency_per_model),
                    lock_expiry=(
                        timezone.now() + datetime.timedelta(seconds=self.lock_expiry)
                    ),
                ):
                    self.tasks.append(
                        asyncio.create_task(self.run_transition(instance))
                    )
                    self.handled[model._meta.label_lower] = (
                        self.handled.get(model._meta.label_lower, 0) + 1
                    )
                    space_remaining -= 1

    async def run_transition(self, instance: StatorModel):
        """
        Wrapper for atransition_attempt with fallback error handling
        """
        task_name = f"stator.run_transition:{instance._meta.label_lower}#{{id}} from {instance.state}"
        async with ThreadSensitiveContext():
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

                try:
                    print(
                        f"Attempting transition on {instance._meta.label_lower}#{instance.pk} from state {instance.state}"
                    )
                    await instance.atransition_attempt()
                except BaseException as e:
                    await exceptions.acapture_exception(e)
                    traceback.print_exc()

    def remove_completed_tasks(self):
        """
        Removes all completed asyncio.Tasks from our local in-progress list
        """
        self.tasks = [t for t in self.tasks if not t.done()]

    async def run_single_cycle(self):
        """
        Testing entrypoint to advance things just one cycle, and allow errors
        to propagate out.
        """
        await asyncio.wait_for(self.fetch_and_process_tasks(), timeout=1)
        for task in self.tasks:
            await task

    run_single_cycle_sync = async_to_sync(run_single_cycle)
