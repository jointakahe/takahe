import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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


class ArticleData(BasePostDataType):
    type: Literal["Article"]
    attributed_to: str | None = Field(...)

    class Config:
        extra = "ignore"


PostDataType = QuestionData | ArticleData


class PostTypeData(BaseModel):
    __root__: PostDataType = Field(discriminator="type")


class PostTypeDataEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, BasePostDataType):
            return obj.dict()
        elif isinstance(obj, datetime):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)


class PostTypeDataDecoder(json.JSONDecoder):
    def decode(self, *args, **kwargs):
        s = super().decode(*args, **kwargs)
        if isinstance(s, dict):
            return PostTypeData.parse_obj(s).__root__
        return s
