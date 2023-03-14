from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views.generic import View

from activities.models.hashtag import Hashtag
from users.decorators import identity_required


@method_decorator(identity_required, name="dispatch")
class HashtagFollow(View):
    """
    Follows/unfollows a hashtag with the current identity
    """

    undo = False

    def post(self, request: HttpRequest, hashtag):
        hashtag = get_object_or_404(
            Hashtag,
            pk=hashtag,
        )
        follow = None
        if self.undo:
            request.identity.hashtag_follows.filter(hashtag=hashtag).delete()
        else:
            follow = request.identity.hashtag_follows.get_or_create(hashtag=hashtag)
        # Return either a redirect or a HTMX snippet
        if request.htmx:
            return render(
                request,
                "activities/_hashtag_follow.html",
                {
                    "hashtag": hashtag,
                    "follow": follow,
                },
            )
        return redirect(hashtag.urls.view)
