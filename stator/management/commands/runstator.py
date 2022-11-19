from typing import List, Type, cast

from asgiref.sync import async_to_sync
from django.apps import apps
from django.core.management.base import BaseCommand

from core.models import Config
from stator.models import StatorModel
from stator.runner import StatorRunner


class Command(BaseCommand):
    help = "Runs a Stator runner"

    def add_arguments(self, parser):
        parser.add_argument(
            "--concurrency",
            "-c",
            type=int,
            default=30,
            help="How many tasks to run at once",
        )
        parser.add_argument(
            "--liveness-file",
            type=str,
            default=None,
            help="A file to touch at least every 30 seconds to say the runner is alive",
        )
        parser.add_argument(
            "--schedule-interval",
            "-s",
            type=int,
            default=30,
            help="How often to run cleaning and scheduling",
        )
        parser.add_argument("model_labels", nargs="*", type=str)

    def handle(
        self,
        model_labels: List[str],
        concurrency: int,
        liveness_file: str,
        schedule_interval: int,
        *args,
        **options
    ):
        # Cache system config
        Config.system = Config.load_system()
        # Resolve the models list into names
        models = cast(
            List[Type[StatorModel]],
            [apps.get_model(label) for label in model_labels],
        )
        if not models:
            models = StatorModel.subclasses
        print("Running for models: " + " ".join(m._meta.label_lower for m in models))
        # Run a runner
        runner = StatorRunner(
            models,
            concurrency=concurrency,
            liveness_file=liveness_file,
            schedule_interval=schedule_interval,
        )
        async_to_sync(runner.run)()
