from typing import List, Type, cast

from asgiref.sync import async_to_sync
from django.apps import apps
from django.core.management.base import BaseCommand

from core.models import Config
from stator.models import StatorModel
from stator.runner import StatorRunner


class Command(BaseCommand):
    help = "Runs a Stator runner for a short period"

    def add_arguments(self, parser):
        parser.add_argument(
            "--concurrency",
            "-c",
            type=int,
            default=30,
            help="How many tasks to run at once",
        )
        parser.add_argument("model_labels", nargs="*", type=str)

    def handle(self, model_labels: List[str], concurrency: int, *args, **options):
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
        runner = StatorRunner(models, concurrency=concurrency)
        async_to_sync(runner.run)()
