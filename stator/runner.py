import asyncio
import datetime
import time
import traceback
import uuid
from typing import List, Optional, Type

from django.conf import settings
from django.utils import timezone

from stator.models import StatorModel


class StatorRunner:
    """
    Runs tasks on models that are looking for state changes.
    Designed to run for a determinate amount of time, and then exit.
    """

    def __init__(
        self,
        models: List[Type[StatorModel]],
        concurrency: int = 50,
        concurrency_per_model: int = 10,
        liveness_file: Optional[str] = None,
        schedule_interval: int = 30,
        lock_expiry: int = 300,
    ):
        self.models = models
        self.runner_id = uuid.uuid4().hex
        self.concurrency = concurrency
        self.concurrency_per_model = concurrency_per_model
        self.liveness_file = liveness_file
        self.schedule_interval = schedule_interval
        self.lock_expiry = lock_expiry

    async def run(self):
        self.handled = 0
        self.last_clean = time.monotonic() - self.schedule_interval
        self.tasks = []
        # For the first time period, launch tasks
        print("Running main task loop")
        try:
            while True:
                # Do we need to do cleaning?
                if (time.monotonic() - self.last_clean) >= self.schedule_interval:
                    print(f"{self.handled} tasks processed so far")
                    print("Running cleaning and scheduling")
                    self.remove_completed_tasks()
                    for model in self.models:
                        asyncio.create_task(model.atransition_clean_locks())
                        asyncio.create_task(model.atransition_schedule_due())
                    self.last_clean = time.monotonic()
                # Calculate space left for tasks
                space_remaining = self.concurrency - len(self.tasks)
                # Fetch new tasks
                for model in self.models:
                    if space_remaining > 0:
                        for instance in await model.atransition_get_with_lock(
                            number=min(space_remaining, self.concurrency_per_model),
                            lock_expiry=(
                                timezone.now()
                                + datetime.timedelta(seconds=self.lock_expiry)
                            ),
                        ):
                            self.tasks.append(
                                asyncio.create_task(self.run_transition(instance))
                            )
                            self.handled += 1
                            space_remaining -= 1
                # Prevent busylooping
                await asyncio.sleep(0.1)
        except KeyboardInterrupt:
            # Wait for tasks to finish
            print("Waiting for tasks to complete")
            while True:
                self.remove_completed_tasks()
                if not self.tasks:
                    break
                # Prevent busylooping
                await asyncio.sleep(1)
        print("Complete")
        return self.handled

    async def run_transition(self, instance: StatorModel):
        """
        Wrapper for atransition_attempt with fallback error handling
        """
        try:
            print(
                f"Attempting transition on {instance._meta.label_lower}#{instance.pk} from state {instance.state}"
            )
            await instance.atransition_attempt()
        except BaseException as e:
            if settings.SENTRY_ENABLED:
                from sentry_sdk import capture_exception

                capture_exception(e)
            traceback.print_exc()

    def remove_completed_tasks(self):
        """
        Removes all completed asyncio.Tasks from our local in-progress list
        """
        self.tasks = [t for t in self.tasks if not t.done()]
