"""Shared signup-verification logic used by both the website (portal app)
and the REST API (api app), so there is one implementation of the
"request a code, then verify it" flow instead of two that can drift apart.
"""
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core import signing
from django.core.mail import send_mail

PENDING_SALT = "eduplatform-pending-signup"
PENDING_MAX_AGE_SECONDS = 600  # 10 minutes - matches EmailVerificationCode's default ttl

MODEL_BY_ROLE = None  # populated lazily to avoid app-loading-order issues


def _model_by_role():
    global MODEL_BY_ROLE
    if MODEL_BY_ROLE is None:
        from users.models import Student, Teacher, Coach
        MODEL_BY_ROLE = {"student": Student, "teacher": Teacher, "coach": Coach}
    return MODEL_BY_ROLE


def send_verification_email(email: str, code: str) -> None:
    """Sends the code. With the console email backend (the default here),
    this prints the message to the server's terminal/log instead of a real
    inbox - swap EMAIL_BACKEND in settings.py for real Gmail SMTP sending
    later without touching this function."""
    send_mail(
        subject="Your verification code",
        message=(
            f"Your Critical Thinking Education Platform verification code is: {code}\n"
            f"It expires in {PENDING_MAX_AGE_SECONDS // 60} minutes."
        ),
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@eduplatform.local"),
        recipient_list=[email],
        fail_silently=False,
    )


def make_pending_signup_token(data: dict) -> str:
    """Hashes the password immediately and signs the rest of the signup
    data into a token the client holds between 'request code' and 'verify
    code' - nothing pending is stored server-side, so it works the same
    whether the caller is a browser (with cookies) or a stateless API
    client like Postman."""
    payload = {
        "role": data["role"],
        "username": data["username"],
        "first_name": data.get("first_name", ""),
        "last_name": data.get("last_name", ""),
        "email": data["email"],
        "password_hash": make_password(data["password"]),
    }
    return signing.dumps(payload, salt=PENDING_SALT, compress=True)


def read_pending_signup_token(token: str) -> dict:
    """Raises signing.SignatureExpired or signing.BadSignature on failure -
    callers should catch those and tell the user to sign up again."""
    return signing.loads(token, salt=PENDING_SALT, max_age=PENDING_MAX_AGE_SECONDS)


def create_role_user_from_payload(payload: dict):
    """Creates the actual Student/Teacher/Coach row from a verified pending
    payload. The password is already hashed, so we set it directly rather
    than calling create_user (which would hash it a second time)."""
    model = _model_by_role()[payload["role"]]
    user = model(
        username=payload["username"],
        email=payload["email"],
        first_name=payload.get("first_name", ""),
        last_name=payload.get("last_name", ""),
    )
    user.password = payload["password_hash"]
    user.save()
    return user
