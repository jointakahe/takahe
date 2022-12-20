from activities.models import Emoji
from api.schemas import CustomEmoji
from api.views.base import api_router


@api_router.get("/v1/custom_emojis", response=list[CustomEmoji])
def emojis(request):
    return [e.to_mastodon_json() for e in Emoji.objects.usable().filter(local=True)]
