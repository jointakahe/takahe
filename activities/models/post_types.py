from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class QuestionOption(BaseModel):
    name: str
    type: Literal["Note"]
    votes: int = 0


class QuestionData(BaseModel):
    type: Literal["Question"]
    mode: Literal["oneOf", "anyOf"] | None = None
    options: list[QuestionOption] | None
    voter_count: int = Field(alias="http://joinmastodon.org/ns#votersCount", default=0)
    end_time: datetime | None = Field(..., alias="endTime")

    class Config:
        extra = "ignore"

    def __init__(self, **data) -> None:
        if "mode" not in data:
            data["mode"] = "anyOf" if "anyOf" in data else "oneOf"
        options = data.pop("anyOf", None)
        if not options:
            options = data.pop("oneOf", None)
        data["options"] = options
        super().__init__(**data)


class ArticleData(BaseModel):
    type: Literal["Article"]
    attributed_to: str | None = Field(...)

    class Config:
        extra = "ignore"


class PostTypeData(BaseModel):
    __root__: QuestionData | ArticleData = Field(discriminator="type")
