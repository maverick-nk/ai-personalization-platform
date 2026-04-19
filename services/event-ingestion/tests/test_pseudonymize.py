from app.pseudonymize import pseudonymize

SECRET = "test-secret"  # noqa: S105


def test_deterministic():
    assert pseudonymize("user-123", SECRET) == pseudonymize("user-123", SECRET)


def test_different_users_produce_different_hashes():
    assert pseudonymize("user-1", SECRET) != pseudonymize("user-2", SECRET)


def test_different_secrets_produce_different_hashes():
    assert pseudonymize("user-123", "secret-a") != pseudonymize("user-123", "secret-b")


def test_output_is_sha256_hex_length():
    assert len(pseudonymize("user-123", SECRET)) == 64


def test_output_is_hex():
    int(pseudonymize("user-123", SECRET), 16)  # raises ValueError if not valid hex


def test_raw_user_id_not_in_output():
    user_id = "user-123"
    assert user_id not in pseudonymize(user_id, SECRET)
