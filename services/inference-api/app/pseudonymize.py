import hashlib
import hmac


def pseudonymize(user_id: str, secret: str) -> str:
    """Replace a raw user ID with a keyed HMAC-SHA256 digest.

    Identical implementation to event-ingestion — both services must produce
    the same digest for the same (user_id, secret) pair so Redis keys and
    privacy records written by event-ingestion are readable here.
    """
    return hmac.new(secret.encode(), user_id.encode(), hashlib.sha256).hexdigest()
