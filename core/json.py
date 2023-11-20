import json

from httpx import Response

JSON_CONTENT_TYPES = [
    "application/json",
    "application/ld+json",
    "application/activity+json",
]


def json_from_response(response: Response) -> dict | None:
    content_type, *parameters = (
        response.headers.get("Content-Type", "invalid").lower().split(";")
    )

    if content_type not in JSON_CONTENT_TYPES:
        return None

    charset = None

    for parameter in parameters:
        key, value = parameter.split("=")
        if key.strip() == "charset":
            charset = value.strip()

    if charset:
        return json.loads(response.content.decode(charset))
    else:
        # if no charset informed, default to
        # httpx json for encoding inference
        return response.json()
