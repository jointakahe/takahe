from types import NoneType, UnionType
from typing import (  # type: ignore[attr-defined]
    Annotated,
    Any,
    Literal,
    Optional,
    TypeVar,
    Union,
    _AnnotatedAlias,
    _GenericAlias,
    get_args,
    get_origin,
)

from django.core import files
from pydantic import BaseModel

from .http import ApiResponse

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


class FileType:
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
File = Annotated[T, FileType]
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
    our_generics = {
        PathType,
        QueryType,
        BodyType,
        FileType,
        BodyDirectType,
        QueryOrBodyType,
    }
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


def extract_output_type(annotation):
    """
    Returns the right response type for a function
    """
    # If the type is ApiResponse, we want to pull out its inside
    if isinstance(annotation, _GenericAlias):
        if get_origin(annotation) == ApiResponse:
            return get_args(annotation)[0]
    return annotation


def acceptable_input(annotation) -> bool:
    """
    Returns if this annotation is something we think we can accept as input
    """
    _, inner_type = extract_signifier(annotation)
    try:
        if issubclass(inner_type, BaseModel):
            return True
    except TypeError:
        pass
    if inner_type in [str, int, list, tuple, bool, Any, files.File, type(None)]:
        return True
    origin = get_origin(inner_type)
    if origin == Literal:
        return True
    if origin in [Union, UnionType, dict, list, tuple]:
        return all(acceptable_input(a) for a in get_args(inner_type))
    return False
