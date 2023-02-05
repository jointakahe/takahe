from typing import Optional, Union

from hatchway.types import Query, QueryType, extract_signifier, is_optional


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
    assert extract_signifier(Query[int]) == (QueryType, int)
    assert extract_signifier(Query[Optional[int]]) == (QueryType, Optional[int])
    assert extract_signifier(Query[int | None]) == (QueryType, Optional[int])
    assert extract_signifier(Optional[Query[int]]) == (QueryType, Optional[int])
