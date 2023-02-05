from typing import Any

from django.db.models import Manager, QuerySet
from django.db.models.fields.files import FieldFile
from django.template import Variable, VariableDoesNotExist
from pydantic.fields import Field  # noqa
from pydantic.main import BaseModel
from pydantic.utils import GetterDict


class DjangoGetterDict(GetterDict):
    def __init__(self, obj: Any):
        self._obj = obj

    def __getitem__(self, key: str) -> Any:
        try:
            item = getattr(self._obj, key)
        except AttributeError:
            try:
                item = Variable(key).resolve(self._obj)
            except VariableDoesNotExist as e:
                raise KeyError(key) from e
        return self._convert_result(item)

    def get(self, key: Any, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def _convert_result(self, result: Any) -> Any:
        if isinstance(result, Manager):
            return list(result.all())

        elif isinstance(result, getattr(QuerySet, "__origin__", QuerySet)):
            return list(result)

        if callable(result):
            return result()

        elif isinstance(result, FieldFile):
            if not result:
                return None
            return result.url

        return result


class Schema(BaseModel):
    class Config:
        orm_mode = True
        getter_dict = DjangoGetterDict
