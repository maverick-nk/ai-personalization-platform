from __future__ import annotations

import hashlib
import hmac


def pseudonymize(user_id: str, secret: str) -> str:
    """HMAC-SHA256 pseudonymization — identical to all service implementations.

    Duplicated here (rather than imported) so the test harness has no dependency
    on any service package. The implementation is 1 line of stdlib.
    """
    return hmac.new(secret.encode(), user_id.encode(), hashlib.sha256).hexdigest()
