import json

import pytest
from django.core import files
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import QueryDict
from django.test import RequestFactory
from django.test.client import MULTIPART_CONTENT
from pydantic import BaseModel

from hatchway import ApiError, Body, QueryOrBody, api_view
from hatchway.view import ApiView


def test_basic_view():
    """
    Tests that a view with simple types works correctly
    """

    @api_view
    def test_view(
        request,
        a: int,
        b: QueryOrBody[int | None] = None,
        c: str = "x",
    ) -> str:
        if b is None:
            return c * a
        else:
            return c * (a - b)

    # Call it with a few different patterns to verify it's type coercing right
    factory = RequestFactory()

    # Implicit query param
    response = test_view(factory.get("/test/?a=4"))
    assert json.loads(response.content) == "xxxx"

    # QueryOrBody pulling from query
    response = test_view(factory.get("/test/?a=4&b=2"))
    assert json.loads(response.content) == "xx"

    # QueryOrBody pulling from formdata body
    response = test_view(factory.post("/test/?a=4", {"b": "3"}))
    assert json.loads(response.content) == "x"

    # QueryOrBody pulling from JSON body
    response = test_view(
        factory.post(
            "/test/?a=4", json.dumps({"b": 3}), content_type="application/json"
        )
    )
    assert json.loads(response.content) == "x"

    # Implicit Query not pulling from body
    with pytest.raises(TypeError):
        test_view(factory.post("/test/", {"a": 4, "b": 3}))


def test_body_direct():
    """
    Tests that a Pydantic model with BodyDirect gets its fields from the top level
    """

    class TestModel(BaseModel):
        number: int
        name: str

    @api_view
    def test_view(request, data: TestModel) -> int:
        return data.number

    factory = RequestFactory()

    # formdata version
    response = test_view(factory.post("/test/", {"number": "123", "name": "Andrew"}))
    assert json.loads(response.content) == 123

    # JSON body version
    response = test_view(
        factory.post(
            "/test/",
            json.dumps({"number": "123", "name": "Andrew"}),
            content_type="application/json",
        )
    )
    assert json.loads(response.content) == 123


def test_list_response():
    """
    Tests that a view with a list response type works correctly with both
    dicts and pydantic model instances.
    """

    class TestModel(BaseModel):
        number: int
        name: str

    @api_view
    def test_view_dict(request) -> list[TestModel]:
        return [
            {"name": "Andrew", "number": 1},  # type:ignore
            {"name": "Alice", "number": 0},  # type:ignore
        ]

    @api_view
    def test_view_model(request) -> list[TestModel]:
        return [TestModel(name="Andrew", number=1), TestModel(name="Alice", number=0)]

    response = test_view_dict(RequestFactory().get("/test/"))
    assert json.loads(response.content) == [
        {"name": "Andrew", "number": 1},
        {"name": "Alice", "number": 0},
    ]

    response = test_view_model(RequestFactory().get("/test/"))
    assert json.loads(response.content) == [
        {"name": "Andrew", "number": 1},
        {"name": "Alice", "number": 0},
    ]


def test_patch_body():
    """
    Tests that PATCH also gets its body parsed
    """

    @api_view.patch
    def test_view(request, a: Body[int]):
        return a

    factory = RequestFactory()
    response = test_view(
        factory.patch(
            "/test/",
            content_type=MULTIPART_CONTENT,
            data=factory._encode_data({"a": "42"}, MULTIPART_CONTENT),
        )
    )
    assert json.loads(response.content) == 42


def test_file_body():
    """
    Tests that file uploads work right
    """

    @api_view.post
    def test_view(request, a: Body[int], b: files.File) -> str:
        return str(a) + b.read().decode("ascii")

    factory = RequestFactory()
    uploaded_file = SimpleUploadedFile(
        "file.txt",
        b"MY FILE IS AMAZING",
        content_type="text/plain",
    )
    response = test_view(
        factory.post(
            "/test/",
            data={"a": 42, "b": uploaded_file},
        )
    )
    assert json.loads(response.content) == "42MY FILE IS AMAZING"


def test_no_response():
    """
    Tests that a view with no response type returns the contents verbatim
    """

    @api_view
    def test_view(request):
        return [1, "woooooo"]

    response = test_view(RequestFactory().get("/test/"))
    assert json.loads(response.content) == [1, "woooooo"]


def test_wrong_method():
    """
    Tests that a view with a method limiter works
    """

    @api_view.get
    def test_view(request):
        return "yay"

    response = test_view(RequestFactory().get("/test/"))
    assert json.loads(response.content) == "yay"

    response = test_view(RequestFactory().post("/test/"))
    assert response.status_code == 405


def test_api_error():
    """
    Tests that ApiError propagates right
    """

    @api_view.get
    def test_view(request):
        raise ApiError(401, "you did a bad thing")

    response = test_view(RequestFactory().get("/test/"))
    assert json.loads(response.content) == {"error": "you did a bad thing"}
    assert response.status_code == 401


def test_unusable_type():
    """
    Tests that you get a nice error when you use a type on an input that
    Pydantic doesn't understand.
    """

    with pytest.raises(ValueError):

        @api_view.get
        def test_view(request, a: RequestFactory):
            pass


def test_get_values():
    """
    Tests that ApiView.get_values correctly handles lists
    """

    assert ApiView.get_values({"a": 2, "b": [3, 4]}) == {"a": 2, "b": [3, 4]}
    assert ApiView.get_values({"a": 2, "b[]": [3, 4]}) == {"a": 2, "b": [3, 4]}
    assert ApiView.get_values(QueryDict("a=2&b=3&b=4")) == {"a": "2", "b": ["3", "4"]}
    assert ApiView.get_values(QueryDict("a=2&b[]=3&b[]=4")) == {
        "a": "2",
        "b": ["3", "4"],
    }
    assert ApiView.get_values(QueryDict("a=2&b=3")) == {"a": "2", "b": "3"}
    assert ApiView.get_values(QueryDict("a=2&b[]=3")) == {"a": "2", "b": ["3"]}
    assert ApiView.get_values(QueryDict("a[b]=1")) == {"a": {"b": "1"}}
    assert ApiView.get_values(QueryDict("a[b]=1&a[c]=2")) == {"a": {"b": "1", "c": "2"}}
    assert ApiView.get_values(QueryDict("a[b][c]=1")) == {"a": {"b": {"c": "1"}}}
    assert ApiView.get_values(QueryDict("a[b][c][]=1")) == {"a": {"b": {"c": ["1"]}}}
    assert ApiView.get_values(QueryDict("a[b][]=1&a[b][]=2")) == {
        "a": {"b": ["1", "2"]}
    }
