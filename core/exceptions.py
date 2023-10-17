class ActivityPubError(BaseException):
    """
    A problem with an ActivityPub message
    """


class ActivityPubFormatError(ActivityPubError):
    """
    A problem with an ActivityPub message's format/keys
    """


class ActorMismatchError(ActivityPubError):
    """
    The actor is not authorised to do the action we saw
    """
