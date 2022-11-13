import pydantic


class Config(pydantic.BaseModel):

    # Basic configuration options
    site_name: str = "takahē"
    identity_max_age: int = 24 * 60 * 60

    # Cached ORM object storage
    __singleton__ = None

    class Config:
        env_prefix = "takahe_"

    @classmethod
    def load(cls) -> "Config":
        if cls.__singleton__ is None:
            cls.__singleton__ = cls()
        return cls.__singleton__
