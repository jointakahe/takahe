from django.conf import settings
from django.http import Http404
from hatchway import ApiError, QueryOrBody, api_view

from api import schemas
from api.decorators import scope_required


@scope_required("push")
@api_view.post
def create_subscription(
    request,
    subscription: QueryOrBody[schemas.PushSubscriptionCreation],
    data: QueryOrBody[schemas.PushData],
) -> schemas.PushSubscription:
    # First, check the server is set up to do push notifications
    if not settings.SETUP.VAPID_PRIVATE_KEY:
        raise Http404("Push not available")
    # Then, register this with our token
    request.token.set_push_subscription(
        {
            "endpoint": subscription.endpoint,
            "keys": subscription.keys,
            "alerts": data.alerts,
            "policy": data.policy,
        }
    )
    # Then return the subscription
    return schemas.PushSubscription.from_token(request.token)  # type:ignore


@scope_required("push")
@api_view.get
def get_subscription(request) -> schemas.PushSubscription:
    # First, check the server is set up to do push notifications
    if not settings.SETUP.VAPID_PRIVATE_KEY:
        raise Http404("Push not available")
    # Get the subscription if it exists
    subscription = schemas.PushSubscription.from_token(request.token)
    if not subscription:
        raise ApiError(404, "Not Found")
    return subscription


@scope_required("push")
@api_view.put
def update_subscription(
    request, data: QueryOrBody[schemas.PushData]
) -> schemas.PushSubscription:
    # First, check the server is set up to do push notifications
    if not settings.SETUP.VAPID_PRIVATE_KEY:
        raise Http404("Push not available")
    # Get the subscription if it exists
    subscription = schemas.PushSubscription.from_token(request.token)
    if not subscription:
        raise ApiError(404, "Not Found")
    # Update the subscription
    subscription.alerts = data.alerts
    subscription.policy = data.policy
    request.token.set_push_subscription(subscription)
    # Then return the subscription
    return schemas.PushSubscription.from_token(request.token)  # type:ignore


@scope_required("push")
@api_view.delete
def delete_subscription(request) -> dict:
    # Unset the subscription
    request.token.push_subscription = None
    return {}
