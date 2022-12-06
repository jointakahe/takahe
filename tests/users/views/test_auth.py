import pytest
from django.core import mail
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
    assertContains(response, "Not accepting new users at this time", status_code=200)
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
    assertNotContains(response, "Not accepting new users at this time")


@pytest.mark.django_db
def test_signup_invite_only(client, config_system):
    """
    Tests that invite codes work with signup
    """
    config_system.signup_allowed = True
    config_system.signup_invite_only = True

    # Try to sign up without an invite code
    response = client.post("/auth/signup/", {"email": "random@example.com"})
    assertNotContains(response, "Email Sent", status_code=200)

    # Make an invite code for any email
    invite_any = Invite.create_random()
    response = client.post(
        "/auth/signup/",
        {"email": "random@example.com", "invite_code": invite_any.token},
    )
    assertNotContains(response, "not a valid invite")
    assertContains(response, "Email Sent", status_code=200)

    # Make sure you can't reuse an invite code
    response = client.post(
        "/auth/signup/",
        {"email": "random2@example.com", "invite_code": invite_any.token},
    )
    assertNotContains(response, "Email Sent", status_code=200)

    # Make an invite code for a specific email
    invite_specific = Invite.create_random(email="special@example.com")
    response = client.post(
        "/auth/signup/",
        {"email": "random3@example.com", "invite_code": invite_specific.token},
    )
    assertContains(response, "valid invite code for this email", status_code=200)
    assertNotContains(response, "Email Sent")
    response = client.post(
        "/auth/signup/",
        {"email": "special@example.com", "invite_code": invite_specific.token},
    )
    assertContains(response, "Email Sent", status_code=200)


@pytest.mark.django_db
def test_signup_policy(client, config_system):
    """
    Tests that you must agree to policies to sign up
    """
    config_system.signup_allowed = True
    config_system.signup_invite_only = False

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
    config_system.signup_invite_only = False

    # Sign up with a user
    response = client.post("/auth/signup/", {"email": "random@example.com"})
    assertContains(response, "Email Sent", status_code=200)

    # Verify that made a user object and a password reset
    user = User.objects.get(email="random@example.com")
    assert user.password_resets.exists()

    # Run Stator and verify it sends the email
    assert len(mail.outbox) == 0
    stator.run_single_cycle_sync()
    assert len(mail.outbox) == 1
