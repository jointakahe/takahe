import json
from datetime import datetime
from typing import Literal

from django.utils import timezone
from pydantic import BaseModel, Field

from core.ld import format_ld_date


class BasePostDataType(BaseModel):
    pass


class QuestionOption(BaseModel):
    name: str
    type: Literal["Note"] = "Note"
    votes: int = 0

    def __init__(self, **data) -> None:
        data["votes"] = data.get("votes", data.get("replies", {}).get("totalItems", 0))

        super().__init__(**data)


class QuestionData(BasePostDataType):
    type: Literal["Question"]
    mode: Literal["oneOf", "anyOf"] | None = None
    options: list[QuestionOption] | None
    voter_count: int = Field(alias="http://joinmastodon.org/ns#votersCount", default=0)
    end_time: datetime | None = Field(alias="endTime")

    class Config:
        extra = "ignore"
        allow_population_by_field_name = True

    def __init__(self, **data) -> None:
        data["voter_count"] = data.get(
            "voter_count", data.get("votersCount", data.get("toot:votersCount", 0))
        )

        if "mode" not in data:
            data["mode"] = "anyOf" if "anyOf" in data else "oneOf"
        if "options" not in data:
            options = data.pop("anyOf", None)
            if not options:
                options = data.pop("oneOf", None)
            data["options"] = options
        super().__init__(**data)

    def to_mastodon_json(self, post, identity=None):
        from activities.models import PostInteraction

        multiple = self.mode == "anyOf"
        value = {
            "id": post.id,
            "expires_at": None,
            "expired": False,
            "multiple": multiple,
            "votes_count": 0,
            "voters_count": self.voter_count,
            "voted": False,
            "own_votes": [],
            "options": [],
            "emojis": [],
        }

        if self.end_time:
            value["expires_at"] = format_ld_date(self.end_time)
            value["expired"] = timezone.now() >= self.end_time

        options = self.options or []
        option_map = {}
        for index, option in enumerate(options):
            value["options"].append(
                {
                    "title": option.name,
                    "votes_count": option.votes,
                }
            )
            value["votes_count"] += option.votes
            option_map[option.name] = index

        if identity:
            votes = post.interactions.filter(
                identity=identity,
                type=PostInteraction.Types.vote,
            )
            value["voted"] = post.author == identity or votes.exists()
            value["own_votes"] = [
                option_map[vote.value] for vote in votes if vote.value in option_map
            ]

        return value


class ArticleData(BasePostDataType):
    type: Literal["Article"]
    attributed_to: str | None = Field(alias="attributedTo")

    class Config:
        extra = "ignore"


PostDataType = QuestionData | ArticleData


class PostTypeData(BaseModel):
    __root__: PostDataType = Field(discriminator="type")


class PostTypeDataEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, BasePostDataType):
            return o.dict()
        elif isinstance(o, datetime):
            return o.isoformat()
        return json.JSONEncoder.default(self, o)


class PostTypeDataDecoder(json.JSONDecoder):
    def decode(self, *args, **kwargs):
        s = super().decode(*args, **kwargs)
        if isinstance(s, dict):
            return PostTypeData.parse_obj(s).__root__
        return s
