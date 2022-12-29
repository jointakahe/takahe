import dataclasses
import urllib.parse

from django.db import models
from django.http import HttpRequest

from activities.models import PostInteraction


@dataclasses.dataclass
class PaginationResult:
    """
    Represents a pagination result for Mastodon (it does Link header stuff)
    """

    #: A list of objects that matched the pagination query.
    results: list[models.Model]

    #: The actual applied limit, which may be different from what was requested.
    limit: int

    @classmethod
    def empty(cls):
        return cls(results=[], limit=20)

    def next(self, request: HttpRequest, allowed_params: list[str]):
        """
        Returns a URL to the next page of results.
        """
        if not self.results:
            return None

        params = self.filter_params(request, allowed_params)
        params["max_id"] = self.results[-1].pk

        return f"{request.build_absolute_uri(request.path)}?{urllib.parse.urlencode(params)}"

    def prev(self, request: HttpRequest, allowed_params: list[str]):
        """
        Returns a URL to the previous page of results.
        """
        if not self.results:
            return None

        params = self.filter_params(request, allowed_params)
        params["min_id"] = self.results[0].pk

        return f"{request.build_absolute_uri(request.path)}?{urllib.parse.urlencode(params)}"

    def link_header(self, request: HttpRequest, allowed_params: list[str]):
        """
        Creates a link header for the given request
        """
        return ", ".join(
            (
                f'<{self.next(request, allowed_params)}>; rel="next"',
                f'<{self.prev(request, allowed_params)}>; rel="prev"',
            )
        )

    @staticmethod
    def filter_params(request: HttpRequest, allowed_params: list[str]):
        params = {}
        for key in allowed_params:
            value = request.GET.get(key, None)
            if value:
                params[key] = value
        return params


class MastodonPaginator:
    """
    Paginates in the Mastodon style (max_id, min_id, etc).
    """

    def __init__(
        self,
        anchor_model: type[models.Model],
        sort_attribute: str = "created",
        default_limit: int = 20,
        max_limit: int = 40,
    ):
        self.anchor_model = anchor_model
        self.sort_attribute = sort_attribute
        self.default_limit = default_limit
        self.max_limit = max_limit

    def get_anchor(self, anchor_id: str):
        """
        Gets an anchor object by ID.
        It's possible that the anchor object might be an interaction, in which
        case we recurse down to its post.
        """
        if anchor_id.startswith("interaction-"):
            try:
                return PostInteraction.objects.get(pk=anchor_id[12:])
            except PostInteraction.DoesNotExist:
                return PaginationResult.empty()
        try:
            return self.anchor_model.objects.get(pk=anchor_id)
        except self.anchor_model.DoesNotExist:
            return PaginationResult.empty()

    def paginate(
        self,
        queryset,
        min_id: str | None,
        max_id: str | None,
        since_id: str | None,
        limit: int | None,
    ) -> PaginationResult:
        if max_id:
            anchor = self.get_anchor(max_id)
            queryset = queryset.filter(
                **{self.sort_attribute + "__lt": getattr(anchor, self.sort_attribute)}
            )

        if since_id:
            anchor = self.get_anchor(since_id)
            queryset = queryset.filter(
                **{self.sort_attribute + "__gt": getattr(anchor, self.sort_attribute)}
            )

        if min_id:
            # Min ID requires items _immediately_ newer than specified, so we
            # invert the ordering to accommodate
            anchor = self.get_anchor(min_id)
            queryset = queryset.filter(
                **{self.sort_attribute + "__gt": getattr(anchor, self.sort_attribute)}
            ).order_by(self.sort_attribute)
        else:
            queryset = queryset.order_by("-" + self.sort_attribute)

        limit = min(limit or self.default_limit, self.max_limit)
        return PaginationResult(
            results=list(queryset[:limit]),
            limit=limit,
        )
