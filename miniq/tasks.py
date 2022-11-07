import traceback

from users.tasks.follow import handle_follow_request
from users.tasks.identity import handle_identity_fetch
from users.tasks.inbox import handle_inbox_item


class TaskHandler:

    handlers = {
        "identity_fetch": handle_identity_fetch,
        "inbox_item": handle_inbox_item,
        "follow_request": handle_follow_request,
    }

    def __init__(self, task):
        self.task = task
        self.subject = self.task.subject
        self.payload = self.task.payload

    async def handle(self):
        try:
            print(f"Task {self.task}: Starting")
            if self.task.type not in self.handlers:
                raise ValueError(f"Cannot handle type {self.task.type}")
            await self.handlers[self.task.type](
                self,
            )
            await self.task.complete()
            print(f"Task {self.task}: Complete")
        except BaseException as e:
            print(f"Task {self.task}: Error {e}")
            traceback.print_exc()
            await self.task.fail(f"{e}\n\n" + traceback.format_exc())
