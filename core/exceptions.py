class ActivityPubError(BaseException):
    """
    A problem with an ActivityPub message
    """


class ActorMismatchError(ActivityPubError):
    """
    The actor is not authorised to do the action we saw
    """
