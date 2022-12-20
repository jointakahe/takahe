class TryAgainLater(BaseException):
    """
    Special exception that Stator will catch without error,
    leaving a state to have another attempt soon.
    """
