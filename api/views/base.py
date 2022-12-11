from ninja import NinjaAPI

from api.parser import FormOrJsonParser

api = NinjaAPI(parser=FormOrJsonParser())
