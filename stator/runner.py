import asyncio
import datetime
import time
import uuid
from typing import List, Type

from asgiref.sync import sync_to_async
from django.db import transaction
from django.utils import timezone

from stator.models import StatorModel, StatorTask


class StatorRunner:
    """
    Runs tasks on models that are looking for state changes.
    Designed to run in a one-shot mode, living inside a request.
    """

    START_TIMEOUT = 30
    TOTAL_TIMEOUT = 60
    LOCK_TIMEOUT = 120

    MAX_TASKS = 30

    def __init__(self, models: List[Type[StatorModel]]):
        self.models = models
        self.runner_id = uuid.uuid4().hex

    async def run(self):
        start_time = time.monotonic()
        self.handled = 0
        self.tasks = []
        # Clean up old locks
        await StatorTask.aclean_old_locks()
        # Examine what needs scheduling

        # For the first time period, launch tasks
        while (time.monotonic() - start_time) < self.START_TIMEOUT:
            self.remove_completed_tasks()
            space_remaining = self.MAX_TASKS - len(self.tasks)
            # Fetch new tasks
            if space_remaining > 0:
                for new_task in await StatorTask.aget_for_execution(
                    space_remaining,
                    timezone.now() + datetime.timedelta(seconds=self.LOCK_TIMEOUT),
                ):
                    self.tasks.append(asyncio.create_task(self.run_task(new_task)))
                    self.handled += 1
            # Prevent busylooping
            await asyncio.sleep(0.01)
        # Then wait for tasks to finish
        while (time.monotonic() - start_time) < self.TOTAL_TIMEOUT:
            self.remove_completed_tasks()
            if not self.tasks:
                break
            # Prevent busylooping
            await asyncio.sleep(1)
        return self.handled

    async def run_task(self, task: StatorTask):
        # Resolve the model instance
        model_instance = await task.aget_model_instance()
        await model_instance.attempt_transition()
        # Remove ourselves from the database as complete
        await task.adelete()

    def remove_completed_tasks(self):
        self.tasks = [t for t in self.tasks if not t.done()]
