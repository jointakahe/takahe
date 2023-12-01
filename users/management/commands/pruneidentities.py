import sys

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from users.models import Identity


class Command(BaseCommand):
    help = "Prunes identities that have no local interaction"

    def add_arguments(self, parser):
        parser.add_argument(
            "--number",
            "-n",
            type=int,
            default=500,
            help="The maximum number of identities to prune at once",
        )

    def handle(self, number: int, *args, **options):
        if not settings.SETUP.REMOTE_PRUNE_HORIZON:
            print("Pruning has been disabled as REMOTE_PRUNE_HORIZON=0")
            sys.exit(2)
        # Find a set of identities that match the initial criteria
        print(f"Running query to find up to {number} unused identities...")
        identities = Identity.objects.filter(
            local=False,
            created__lt=timezone.now(),
        ).exclude(
            Q(interactions__post__local=True)
            | Q(posts__isnull=False)
            | Q(posts_mentioning__isnull=False)
            | Q(outbound_follows__isnull=False)
            | Q(inbound_follows__isnull=False)
            | Q(outbound_blocks__isnull=False)
            | Q(inbound_blocks__isnull=False)
        )[
            :number
        ]
        identity_ids = identities.values_list("id", flat=True)
        print(f"  found {len(identity_ids)}")
        if not identity_ids:
            sys.exit(0)

        # Delete them
        print("Deleting...")
        number_deleted, deleted = Identity.objects.filter(id__in=identity_ids).delete()
        print("Deleted:")
        for model, model_deleted in deleted.items():
            print(f"  {model}: {model_deleted}")
        sys.exit(1)
