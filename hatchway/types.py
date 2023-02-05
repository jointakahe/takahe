from types import NoneType, UnionType
from typing import (  # type: ignore[attr-defined]
    Annotated,
    Any,
    Optional,
    TypeVar,
    Union,
    _AnnotatedAlias,
    _GenericAlias,
    get_args,
)

T = TypeVar("T")


class PathType:
    """
    An input pulled from the path (url resolver kwargs)
    """


class QueryType:
    """
    An input pulled from the query parameters (request.GET)
    """


class BodyType:
    """
    An input pulled from the POST body (request.POST or a JSON body)
    """


class BodyDirectType:
    """
    A Pydantic model whose keys are all looked for in the top-level
    POST data, rather than in a dict under a key named after the input.
    """


class QueryOrBodyType:
    """
    An input pulled from either query parameters or post data.
    """


Path = Annotated[T, PathType]
Query = Annotated[T, QueryType]
Body = Annotated[T, BodyType]
BodyDirect = Annotated[T, BodyDirectType]
QueryOrBody = Annotated[T, QueryOrBodyType]


def is_optional(annotation) -> tuple[bool, Any]:
    """
    If an annotation is Optional or | None, returns (True, internal type).
    Returns (False, annotation) otherwise.
    """
    if (isinstance(annotation, _GenericAlias) and annotation.__origin__ is Union) or (
        isinstance(annotation, UnionType)
    ):
        args = get_args(annotation)
        if len(args) > 2:
            return False, annotation
        if args[0] is NoneType:
            return True, args[1]
        if args[1] is NoneType:
            return True, args[0]
        return False, annotation
    return False, annotation


def extract_signifier(annotation) -> tuple[Any, Any]:
    """
    Given a type annotation, looks to see if it can find a input source
    signifier (Path, Query, etc.)

    If it can, returns (signifier, annotation_without_signifier)
    If not, returns (None, annotation)
    """
    our_generics = {PathType, QueryType, BodyType, BodyDirectType, QueryOrBodyType}
    # Remove any optional-style wrapper
    optional, internal_annotation = is_optional(annotation)
    # Is it an annotation?
    if isinstance(internal_annotation, _AnnotatedAlias):
        args = get_args(internal_annotation)
        for arg in args[1:]:
            if arg in our_generics:
                if optional:
                    return (arg, Optional[args[0]])
                else:
                    return (arg, args[0])
    return None, annotation
