import asyncio
import time
import uuid

from asgiref.sync import sync_to_async
from django.http import HttpResponse
from django.views import View

from miniq.models import Task
from miniq.tasks import TaskHandler


class QueueProcessor(View):
    """
    A view that takes some items off the queue and processes them.
    Tries to limit its own runtime so it's within HTTP timeout limits.
    """

    START_TIMEOUT = 30
    TOTAL_TIMEOUT = 60
    LOCK_TIMEOUT = 200
    MAX_TASKS = 20

    async def get(self, request):
        start_time = time.monotonic()
        processor_id = uuid.uuid4().hex
        handled = 0
        self.tasks = []
        # For the first time period, launch tasks
        while (time.monotonic() - start_time) < self.START_TIMEOUT:
            # Remove completed tasks
            self.tasks = [t for t in self.tasks if not t.done()]
            # See if there's a new task
            if len(self.tasks) < self.MAX_TASKS:
                # Pop a task off the queue and run it
                task = await sync_to_async(Task.get_one_available)(processor_id)
                if task is not None:
                    self.tasks.append(asyncio.create_task(TaskHandler(task).handle()))
                    handled += 1
            # Prevent busylooping
            await asyncio.sleep(0.01)
        # TODO: Clean up old locks here
        # Then wait for tasks to finish
        while (time.monotonic() - start_time) < self.TOTAL_TIMEOUT:
            # Remove completed tasks
            self.tasks = [t for t in self.tasks if not t.done()]
            if not self.tasks:
                break
            # Prevent busylooping
            await asyncio.sleep(1)
        return HttpResponse(f"{handled} tasks handled")
