import json
from collections.abc import Callable
from typing import Any, Optional, get_type_hints

from django.core import files
from django.http import HttpRequest, HttpResponseNotAllowed, QueryDict
from django.http.multipartparser import MultiPartParser
from pydantic import BaseModel, create_model

from .constants import InputSource
from .http import ApiError, ApiResponse
from .types import (
    BodyDirectType,
    BodyType,
    FileType,
    PathType,
    QueryOrBodyType,
    QueryType,
    acceptable_input,
    extract_output_type,
    extract_signifier,
    is_optional,
)


class ApiView:
    """
    A view 'wrapper' object that replaces the API view for anything further
    up the stack.

    Unlike Django's class-based views, we don't need an as_view pattern
    as we are careful never to write anything per-request to self.
    """

    csrf_exempt = True

    def __init__(
        self,
        view: Callable,
        input_types: dict[str, Any] | None = None,
        output_type: Any = None,
        implicit_lists: bool = True,
        method: str | None = None,
    ):
        self.view = view
        self.implicit_lists = implicit_lists
        self.view_name = getattr(view, "__name__", "unknown_view")
        self.method = method
        # Extract input/output types from view annotations if we need to
        self.input_types = input_types
        if self.input_types is None:
            self.input_types = get_type_hints(view, include_extras=True)
            if "return" in self.input_types:
                del self.input_types["return"]
        self.output_type = output_type
        if self.output_type is None:
            try:
                self.output_type = extract_output_type(
                    get_type_hints(view, include_extras=True)["return"]
                )
            except KeyError:
                self.output_type = None
        self.compile()

    @classmethod
    def get(cls, view: Callable):
        return cls(view=view, method="get")

    @classmethod
    def post(cls, view: Callable):
        return cls(view=view, method="post")

    @classmethod
    def put(cls, view: Callable):
        return cls(view=view, method="put")

    @classmethod
    def patch(cls, view: Callable):
        return cls(view=view, method="patch")

    @classmethod
    def delete(cls, view: Callable):
        return cls(view=view, method="delete")

    @classmethod
    def sources_for_input(cls, input_type) -> tuple[list[InputSource], Any]:
        """
        Given a type that can appear as a request parameter type, returns
        what sources it can come from, and what its type is as understood
        by Pydantic.
        """
        signifier, input_type = extract_signifier(input_type)
        if signifier is QueryType:
            return ([InputSource.query], input_type)
        elif signifier is BodyType:
            return ([InputSource.body], input_type)
        elif signifier is BodyDirectType:
            if not issubclass(input_type, BaseModel):
                raise ValueError(
                    "You cannot use BodyDirect on something that is not a Pydantic model"
                )
            return ([InputSource.body_direct], input_type)
        elif signifier is PathType:
            return ([InputSource.path], input_type)
        elif (
            signifier is FileType
            or input_type is files.File
            or is_optional(input_type)[1] is files.File
        ):
            return ([InputSource.file], input_type)
        elif signifier is QueryOrBodyType:
            return ([InputSource.query, InputSource.body], input_type)
        # Is it a Pydantic model, which means it's implicitly body?
        elif isinstance(input_type, type) and issubclass(input_type, BaseModel):
            return ([InputSource.body], input_type)
        # Otherwise, we look in the path first and then the query
        else:
            return ([InputSource.path, InputSource.query], input_type)

    @classmethod
    def get_values(cls, data, use_square_brackets=True) -> dict[str, Any]:
        """
        Given a QueryDict or normal dict, returns data taking into account
        lists made by repeated values or by suffixing names with [].
        """
        result: dict[str, Any] = {}
        for key, value in data.items():
            # If it's a query dict with multiple values, make it a list
            if isinstance(data, QueryDict):
                values = data.getlist(key)
                if len(values) > 1:
                    value = values
            # If it is in dict-ish/list-ish syntax, adhere to that
            # TODO: Make this better handle badly formed keys
            if "[" in key and use_square_brackets:
                parts = key.split("[")
                target = result
                last_key = parts[0]
                for part in parts[1:]:
                    part = part.rstrip("]")
                    if not part:
                        target = target.setdefault(last_key, [])
                    else:
                        target = target.setdefault(last_key, {})
                        last_key = part
                if isinstance(target, list):
                    if isinstance(value, list):
                        target.extend(value)
                    else:
                        target.append(value)
                else:
                    target[last_key] = value
            else:
                result[key] = value
        return result

    def compile(self):
        self.sources: dict[str, list[InputSource]] = {}
        amount_from_body = 0
        pydantic_model_dict = {}
        self.input_files = set()
        last_body_type = None
        # For each input item, work out where to pull it from
        for name, input_type in self.input_types.items():
            # Do some basic typechecking to stop things that aren't allowed
            if isinstance(input_type, type) and issubclass(input_type, HttpRequest):
                continue
            if not acceptable_input(input_type):
                # Strip away any singifiers for the error
                _, inner_type = extract_signifier(input_type)
                raise ValueError(
                    f"Input argument {name} has an unsupported type {inner_type}"
                )
            sources, pydantic_type = self.sources_for_input(input_type)
            self.sources[name] = sources
            # Keep count of how many are pulling from the body
            if InputSource.body in sources:
                amount_from_body += 1
                last_body_type = pydantic_type
            if InputSource.file in sources:
                self.input_files.add(name)
            else:
                pydantic_model_dict[name] = (Optional[pydantic_type], ...)
        # If there is just one thing pulling from the body and it's a BaseModel,
        # signify that it's actually pulling from the body keys directly and
        # not a sub-dict
        if amount_from_body == 1:
            for name, sources in self.sources.items():
                if (
                    InputSource.body in sources
                    and isinstance(last_body_type, type)
                    and issubclass(last_body_type, BaseModel)
                ):
                    self.sources[name] = [
                        x for x in sources if x != InputSource.body
                    ] + [InputSource.body_direct]
        # Turn all the main arguments into Pydantic parsing models
        try:
            self.input_model = create_model(
                f"{self.view_name}_input", **pydantic_model_dict
            )
        except RuntimeError:
            raise ValueError(
                f"One or more inputs on view {self.view_name} have a bad configuration"
            )
        if self.output_type is not None:
            self.output_model = create_model(
                f"{self.view_name}_output", value=(self.output_type, ...)
            )

    def __call__(self, request: HttpRequest, *args, **kwargs):
        """
        Entrypoint when this is called as a view.
        """
        # Do a method check if we have one set
        if self.method and self.method.upper() != request.method:
            return HttpResponseNotAllowed([self.method])
        # For each item we can source, go find it if we can
        query_values = self.get_values(request.GET)
        body_values = self.get_values(request.POST)
        files_values = self.get_values(request.FILES)
        # If it's a PUT or PATCH method, work around Django not handling FILES
        # or POST on those requests
        if request.method in ["PATCH", "PUT"]:
            if request.content_type == "multipart/form-data":
                POST, FILES = MultiPartParser(
                    request.META, request, request.upload_handlers, request.encoding
                ).parse()
                body_values = self.get_values(POST)
                files_values = self.get_values(FILES)
            elif request.content_type == "application/x-www-form-urlencoded":
                POST = QueryDict(request.body, encoding=request._encoding)
                body_values = self.get_values(POST)
        # If there was a JSON body, go load that
        if request.content_type == "application/json" and request.body.strip():
            body_values.update(self.get_values(json.loads(request.body)))
        values = {}
        for name, sources in self.sources.items():
            for source in sources:
                if source == InputSource.path:
                    if name in kwargs:
                        values[name] = kwargs[name]
                        break
                elif source == InputSource.query:
                    if name in query_values:
                        values[name] = query_values[name]
                        break
                elif source == InputSource.body:
                    if name in body_values:
                        values[name] = body_values[name]
                        break
                elif source == InputSource.file:
                    if name in files_values:
                        values[name] = files_values[name]
                        break
                elif source == InputSource.body_direct:
                    values[name] = body_values
                    break
                elif source == InputSource.query_and_body_direct:
                    values[name] = dict(query_values)
                    values[name].update(body_values)
                    break
                else:
                    raise ValueError(f"Unknown source {source}")
            else:
                values[name] = None
        # Give that to the Pydantic model to make it handle stuff
        model_instance = self.input_model(**values)
        kwargs = {
            name: getattr(model_instance, name)
            for name in model_instance.__fields__
            if values[name] is not None  # Trim out missing fields
        }
        # Add in any files
        # TODO: HTTP error if file is not optional
        for name in self.input_files:
            kwargs[name] = files_values.get(name, None)
        # Call the view with those as kwargs
        try:
            response = self.view(request, **kwargs)
        except ApiError as error:
            return ApiResponse(
                {"error": error.error}, status=error.status, finalize=True
            )
        # If it's not an ApiResponse, make it one
        if not isinstance(response, ApiResponse):
            response = ApiResponse(response)
        # Get pydantic to coerce the output response
        if self.output_type is not None:
            response.data = self.output_model(value=response.data).dict()["value"]
        elif isinstance(response.data, BaseModel):
            response.data = response.data.dict()
        response.finalize()
        return response


api_view = ApiView
