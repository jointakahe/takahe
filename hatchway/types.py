from types import NoneType, UnionType
from typing import (  # type: ignore[attr-defined]
    Any,
    Generic,
    Optional,
    TypeVar,
    Union,
    _GenericAlias,
)

T = TypeVar("T")


class Path(Generic[T]):
    """
    An input pulled from the path (url resolver kwargs)
    """


class Query(Generic[T]):
    """
    An input pulled from the query parameters (request.GET)
    """


class Body(Generic[T]):
    """
    An input pulled from the POST body (request.POST or a JSON body)
    """


class BodyDirect(Generic[T]):
    """
    A Pydantic model whose keys are all looked for in the top-level
    POST data, rather than in a dict under a key named after the input.
    """


class QueryOrBody(Generic[T]):
    """
    An input pulled from either query parameters or post data.
    """


def is_optional(annotation) -> tuple[bool, Any]:
    """
    If an annotation is Optional or | None, returns (True, internal type).
    Returns (False, annotation) otherwise.
    """
    if (isinstance(annotation, _GenericAlias) and annotation.__origin__ is Union) or (
        isinstance(annotation, UnionType)
    ):
        args = annotation.__args__
        if len(args) > 2:
            return False, annotation
        if args[0] is NoneType:
            return True, args[1]
        if args[1] is NoneType:
            return True, args[0]
        return False, annotation
    return False, annotation


def get_params(annotation) -> tuple:
    """
    Returns the parameters from within an annotation
    """
    if isinstance(annotation, _GenericAlias):
        return annotation.__args__
    raise ValueError(f"{annotation} is not a parameterised type")


def extract_signifier(annotation) -> tuple[Any, Any]:
    """
    Given a type annotation, looks a couple of levels deep to see if it
    can find a Path, Query, Body, etc. type annotation.

    If it can, returns (signifier, annotation_without_signifier)
    If not, returns (None, annotation)
    """
    our_generics = {Path, Query, Body, BodyDirect, QueryOrBody}
    # Unwrap any Optional wrapper for now
    optional, internal_annotation = is_optional(annotation)
    # Is the annotation one of ours?
    if isinstance(internal_annotation, _GenericAlias):
        if internal_annotation.__origin__ in our_generics:
            if optional:
                return (
                    internal_annotation.__origin__,
                    Optional[internal_annotation.__args__[0]],
                )
            else:
                return internal_annotation.__origin__, internal_annotation.__args__[0]
    return None, annotation
