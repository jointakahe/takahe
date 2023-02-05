import enum


class InputSource(str, enum.Enum):
    path = "path"
    query = "query"
    body = "body"
    body_direct = "body_direct"
    query_and_body_direct = "query_and_body_direct"
    file = "file"
