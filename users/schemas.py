from typing import Any, Literal

from pydantic import BaseModel, Field


class NodeInfoServices(BaseModel):
    inbound: list[str]
    outbound: list[str]


class NodeInfoSoftware(BaseModel):
    name: str
    version: str = "unknown"


class NodeInfoUsage(BaseModel):
    users: dict[str, int | None] | None
    local_posts: int = Field(default=0, alias="localPosts")


class NodeInfo(BaseModel):

    version: Literal["2.0"]
    software: NodeInfoSoftware
    protocols: list[str] | None
    open_registrations: bool = Field(alias="openRegistrations")
    usage: NodeInfoUsage

    metadata: dict[str, Any] | None

    class Config:
        extra = "ignore"
