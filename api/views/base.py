from ninja import NinjaAPI

from api.parser import FormOrJsonParser

api_router = NinjaAPI(parser=FormOrJsonParser())
