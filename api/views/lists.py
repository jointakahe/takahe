from typing import Literal

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from hatchway import Schema, api_view

from api import schemas
from api.decorators import scope_required


class CreateList(Schema):
    title: str
    replies_policy: Literal["followed", "list", "none"] = "list"
    exclusive: bool = False


class UpdateList(Schema):
    title: str | None
    replies_policy: Literal["followed", "list", "none"] | None
    exclusive: bool | None


@scope_required("read:lists")
@api_view.get
def get_lists(request: HttpRequest) -> list[schemas.List]:
    return [schemas.List.from_list(lst) for lst in request.identity.lists.all()]


@scope_required("write:lists")
@api_view.post
def create_list(request: HttpRequest, data: CreateList) -> schemas.List:
    created = request.identity.lists.create(
        title=data.title,
        replies_policy=data.replies_policy,
        exclusive=data.exclusive,
    )
    return schemas.List.from_list(created)


@scope_required("read:lists")
@api_view.get
def get_list(request: HttpRequest, id: str) -> schemas.List:
    alist = get_object_or_404(request.identity.lists, pk=id)
    return schemas.List.from_list(alist)


@scope_required("write:lists")
@api_view.put
def update_list(request: HttpRequest, id: str, data: UpdateList) -> schemas.List:
    alist = get_object_or_404(request.identity.lists, pk=id)
    if data.title:
        alist.title = data.title
    if data.replies_policy:
        alist.replies_policy = data.replies_policy
    if data.exclusive is not None:
        alist.exclusive = data.exclusive
    alist.save()
    return schemas.List.from_list(alist)


@scope_required("write:lists")
@api_view.delete
def delete_list(request: HttpRequest, id: str) -> dict:
    alist = get_object_or_404(request.identity.lists, pk=id)
    alist.delete()
    return {}


@scope_required("write:lists")
@api_view.get
def get_accounts(request: HttpRequest, id: str) -> list[schemas.Account]:
    alist = get_object_or_404(request.identity.lists, pk=id)
    return [schemas.Account.from_identity(ident) for ident in alist.members.all()]


@scope_required("write:lists")
@api_view.post
def add_accounts(request: HttpRequest, id: str) -> dict:
    alist = get_object_or_404(request.identity.lists, pk=id)
    add_ids = request.PARAMS.get("account_ids")
    for follow in request.identity.outbound_follows.filter(
        target__id__in=add_ids
    ).select_related("target"):
        alist.members.add(follow.target)
    return {}


@scope_required("write:lists")
@api_view.delete
def delete_accounts(request: HttpRequest, id: str) -> dict:
    alist = get_object_or_404(request.identity.lists, pk=id)
    remove_ids = request.PARAMS.get("account_ids")
    for ident in alist.members.filter(id__in=remove_ids):
        alist.members.remove(ident)
    return {}
