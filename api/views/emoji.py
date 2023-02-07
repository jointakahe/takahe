from activities.models import Emoji
from api.schemas import CustomEmoji
from hatchway import api_view


@api_view.get
def emojis(request) -> list[CustomEmoji]:
    return [
        CustomEmoji.from_emoji(e) for e in Emoji.objects.usable().filter(local=True)
    ]
