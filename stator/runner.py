import asyncio
import datetime
import time
import traceback
import uuid
from typing import List, Type

from django.utils import timezone

from stator.models import StatorModel


class StatorRunner:
    """
    Runs tasks on models that are looking for state changes.
    Designed to run in a one-shot mode, living inside a request.
    """

    def __init__(
        self,
        models: List[Type[StatorModel]],
        concurrency: int = 30,
        concurrency_per_model: int = 5,
        run_period: int = 30,
        wait_period: int = 30,
    ):
        self.models = models
        self.runner_id = uuid.uuid4().hex
        self.concurrency = concurrency
        self.concurrency_per_model = concurrency_per_model
        self.run_period = run_period
        self.total_period = run_period + wait_period

    async def run(self):
        start_time = time.monotonic()
        self.handled = 0
        self.tasks = []
        # Clean up old locks
        print("Running initial cleaning and scheduling")
        initial_tasks = []
        for model in self.models:
            initial_tasks.append(model.atransition_clean_locks())
            initial_tasks.append(model.atransition_schedule_due())
        await asyncio.gather(*initial_tasks)
        # For the first time period, launch tasks
        print("Running main task loop")
        while (time.monotonic() - start_time) < self.run_period:
            self.remove_completed_tasks()
            space_remaining = self.concurrency - len(self.tasks)
            # Fetch new tasks
            for model in self.models:
                if space_remaining > 0:
                    for instance in await model.atransition_get_with_lock(
                        number=min(space_remaining, self.concurrency_per_model),
                        lock_expiry=(
                            timezone.now()
                            + datetime.timedelta(seconds=(self.total_period * 2) + 60)
                        ),
                    ):
                        self.tasks.append(
                            asyncio.create_task(self.run_transition(instance))
                        )
                        self.handled += 1
                        space_remaining -= 1
            # Prevent busylooping
            await asyncio.sleep(0.1)
        # Then wait for tasks to finish
        print("Waiting for tasks to complete")
        while (time.monotonic() - start_time) < self.total_period:
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
        except BaseException:
            traceback.print_exc()

    def remove_completed_tasks(self):
        """
        Removes all completed asyncio.Tasks from our local in-progress list
        """
        self.tasks = [t for t in self.tasks if not t.done()]
