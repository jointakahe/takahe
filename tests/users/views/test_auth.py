import datetime

import pytest
from django.core import mail
from django.utils import timezone
from pytest_django.asserts import assertContains, assertNotContains

from users.models import Invite, User


@pytest.mark.django_db
def test_signup_disabled(client, config_system):
    """
    Tests that disabling signup takes effect
    """
    # Signup disabled and no signup text
    config_system.signup_allowed = False
    response = client.get("/auth/signup/")
    assertContains(
        response, "We're not accepting new users at this time", status_code=200
    )
    assertNotContains(response, "<button>Create</button>")

    # Signup disabled with signup text configured
    config_system.signup_text = "Go away!!!!!!"
    response = client.get("/auth/signup/")
    assertContains(response, "Go away!!!!!!", status_code=200)

    # Ensure direct POST doesn't side step guard
    response = client.post(
        "/auth/signup/", data={"email": "test_signup_disabled@example.org"}
    )
    assert response.status_code == 200
    assert not User.objects.filter(email="test_signup_disabled@example.org").exists()

    # Signup enabled
    config_system.signup_allowed = True
    response = client.get("/auth/signup/")
    assertContains(response, "<button>Create</button>", status_code=200)
    assertNotContains(response, "We're not accepting new users at this time")


@pytest.mark.django_db
def test_signup_invite_only(client, config_system):
    """
    Tests that invite codes work with signup
    """
    config_system.signup_allowed = False

    # Try to sign up without an invite code
    response = client.post("/auth/signup/", {"email": "random@example.com"})
    assertNotContains(response, "Email Sent", status_code=200)

    # Make an invite code for any email with infinite uses
    invite_infinite = Invite.create_random()
    response = client.post(
        f"/auth/signup/{invite_infinite.token}/",
        {"email": "random@example.com"},
    )
    assertContains(response, "Email Sent", status_code=200)

    # Ensure it still has infinite uses
    assert Invite.objects.get(token=invite_infinite.token).uses is None

    # Make an invite code for any email with one use
    invite_single = Invite.create_random(uses=1)
    response = client.post(
        f"/auth/signup/{invite_single.token}/",
        {"email": "random2@example.com"},
    )
    assertContains(response, "Email Sent", status_code=200)

    # Verify it was used up
    assert Invite.objects.filter(token=invite_single.token).count() == 0

    # Make an invite code that's invalid
    invite_expired = Invite.create_random(
        expires=timezone.now() - datetime.timedelta(days=1)
    )
    response = client.post(
        f"/auth/signup/{invite_expired.token}/",
        {"email": "random3@example.com"},
    )
    print(response.content)
    assert response.status_code == 404


@pytest.mark.django_db
def test_signup_policy(client, config_system):
    """
    Tests that you must agree to policies to sign up
    """
    config_system.signup_allowed = True

    # Make sure we can sign up when there are no policies
    response = client.post("/auth/signup/", {"email": "random@example.com"})
    assertContains(response, "Email Sent", status_code=200)

    # Make sure that's then denied when we have a policy in place
    config_system.policy_rules = "You must love unit tests"
    response = client.post("/auth/signup/", {"email": "random2@example.com"})
    assertContains(response, "field is required", status_code=200)
    assertNotContains(response, "Email Sent")


@pytest.mark.django_db
def test_signup_email(client, config_system, stator):
    """
    Tests that you can sign up and get an email sent to you
    """
    config_system.signup_allowed = True

    # Sign up with a user
    response = client.post("/auth/signup/", {"email": "random@example.com"})
    assertContains(response, "Email Sent", status_code=200)

    # Verify that made a user object and a password reset
    user = User.objects.get(email="random@example.com")
    assert user.password_resets.exists()

    # Run Stator and verify it sends the email
    assert len(mail.outbox) == 0
    stator.run_single_cycle()
    assert len(mail.outbox) == 1
