from app.pseudonymize import pseudonymize


def test_deterministic():
    assert pseudonymize("user123", "secret") == pseudonymize("user123", "secret")


def test_different_users_differ():
    assert pseudonymize("user1", "secret") != pseudonymize("user2", "secret")


def test_different_secrets_differ():
    assert pseudonymize("user1", "secret-a") != pseudonymize("user1", "secret-b")


def test_output_is_hex_string():
    result = pseudonymize("user1", "secret")
    assert isinstance(result, str)
    assert len(result) == 64
    int(result, 16)  # raises ValueError if not valid hex
