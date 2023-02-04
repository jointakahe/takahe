from typing import Optional, Union

from hatchway.types import Query, extract_signifier, is_optional


def test_is_optional():

    assert is_optional(Optional[int]) == (True, int)
    assert is_optional(Union[int, None]) == (True, int)
    assert is_optional(Union[None, int]) == (True, int)
    assert is_optional(int | None) == (True, int)
    assert is_optional(None | int) == (True, int)
    assert is_optional(int) == (False, int)
    assert is_optional(Query[int]) == (False, Query[int])


def test_extract_signifier():

    assert extract_signifier(int) == (None, int)
    assert extract_signifier(Query[int]) == (Query, int)
    assert extract_signifier(Optional[Query[int]]) == (Query, Optional[int])
    assert extract_signifier(Query[int] | None) == (Query, Optional[int])
