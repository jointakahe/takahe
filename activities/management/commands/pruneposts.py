import datetime
import sys

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from activities.models import Post


class Command(BaseCommand):
    help = "Prunes posts that are old, not local and have no local interaction"

    def add_arguments(self, parser):
        parser.add_argument(
            "--number",
            "-n",
            type=int,
            default=500,
            help="The maximum number of posts to prune at once",
        )

    def handle(self, number: int, *args, **options):
        if not settings.SETUP.REMOTE_PRUNE_HORIZON:
            print("Pruning has been disabled as REMOTE_PRUNE_HORIZON=0")
            sys.exit(2)
        # Find a set of posts that match the initial criteria
        print(f"Running query to find up to {number} old posts...")
        posts = (
            Post.objects.filter(
                local=False,
                created__lt=timezone.now()
                - datetime.timedelta(days=settings.SETUP.REMOTE_PRUNE_HORIZON),
            )
            .exclude(
                Q(interactions__identity__local=True)
                | Q(visibility=Post.Visibilities.mentioned)
            )
            .order_by("?")[:number]
        )
        post_ids_and_uris = dict(posts.values_list("object_uri", "id"))
        print(f"  found {len(post_ids_and_uris)}")

        # Fetch all of their replies and exclude any that have local replies
        print("Excluding ones with local replies...")
        replies = Post.objects.filter(
            local=True,
            in_reply_to__in=post_ids_and_uris.keys(),
        ).values_list("in_reply_to", flat=True)
        for reply in replies:
            if reply and reply in post_ids_and_uris:
                del post_ids_and_uris[reply]
        print(f"  narrowed down to {len(post_ids_and_uris)}")

        # Fetch all the posts that they are replies to, and don't delete ones
        # that are replies to local posts
        print("Excluding ones that are replies to local posts...")
        in_reply_tos = (
            Post.objects.filter(id__in=post_ids_and_uris.values())
            .values_list("in_reply_to", flat=True)
            .distinct()
        )
        local_object_uris = Post.objects.filter(
            local=True, object_uri__in=in_reply_tos
        ).values_list("object_uri", flat=True)
        final_post_ids = list(
            Post.objects.filter(id__in=post_ids_and_uris.values())
            .exclude(in_reply_to__in=local_object_uris)
            .values_list("id", flat=True)
        )
        print(f"  narrowed down to {len(final_post_ids)}")

        # Delete them
        if not final_post_ids:
            sys.exit(0)

        print("Deleting...")
        _, deleted = Post.objects.filter(id__in=final_post_ids).delete()
        print("Deleted:")
        for model, model_deleted in deleted.items():
            print(f"  {model}: {model_deleted}")
        sys.exit(1)
