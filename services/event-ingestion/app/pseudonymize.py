import hashlib
import hmac


def pseudonymize(user_id: str, secret: str) -> str:
    """Replace a raw user ID with a keyed HMAC-SHA256 digest.

    This is the privacy boundary: raw user IDs must never appear in Kafka topics,
    Redis, Parquet, or logs. All downstream services (feature pipeline, inference API,
    privacy service) operate exclusively on the returned hex digest.

    HMAC is used instead of a plain hash so the mapping cannot be reversed or
    pre-computed without knowledge of the secret. The same user_id + secret always
    produces the same digest, allowing consistent feature lookups across services.
    """
    return hmac.new(secret.encode(), user_id.encode(), hashlib.sha256).hexdigest()
