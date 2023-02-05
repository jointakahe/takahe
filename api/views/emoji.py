from activities.models import Emoji
from api.schemas import CustomEmoji
from hatchway import api_view


@api_view.get
def emojis(request) -> list[CustomEmoji]:
    return [e.to_mastodon_json() for e in Emoji.objects.usable().filter(local=True)]
