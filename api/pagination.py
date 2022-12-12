from django.db import models


class MastodonPaginator:
    """
    Paginates in the Mastodon style (max_id, min_id, etc)
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

    def paginate(
        self,
        queryset,
        min_id: str | None,
        max_id: str | None,
        since_id: str | None,
        limit: int | None,
    ):
        if max_id:
            try:
                anchor = self.anchor_model.objects.get(pk=max_id)
            except self.anchor_model.DoesNotExist:
                return []
            queryset = queryset.filter(
                **{self.sort_attribute + "__lt": getattr(anchor, self.sort_attribute)}
            )
        if since_id:
            try:
                anchor = self.anchor_model.objects.get(pk=since_id)
            except self.anchor_model.DoesNotExist:
                return []
            queryset = queryset.filter(
                **{self.sort_attribute + "__gt": getattr(anchor, self.sort_attribute)}
            )
        if min_id:
            # Min ID requires items _immediately_ newer than specified, so we
            # invert the ordering to accomodate
            try:
                anchor = self.anchor_model.objects.get(pk=min_id)
            except self.anchor_model.DoesNotExist:
                return []
            queryset = queryset.filter(
                **{self.sort_attribute + "__gt": getattr(anchor, self.sort_attribute)}
            ).order_by(self.sort_attribute)
        else:
            queryset = queryset.order_by("-" + self.sort_attribute)
        return list(queryset[: min(limit or self.default_limit, self.max_limit)])
