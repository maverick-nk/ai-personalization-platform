from app.pseudonymize import pseudonymize


def test_deterministic():
    assert pseudonymize("user1", "secret") == pseudonymize("user1", "secret")


def test_different_users_produce_different_digests():
    assert pseudonymize("user1", "secret") != pseudonymize("user2", "secret")


def test_different_secrets_produce_different_digests():
    assert pseudonymize("user1", "secret-a") != pseudonymize("user1", "secret-b")


def test_output_is_64_char_hex():
    digest = pseudonymize("user1", "secret")
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_raw_user_id_not_in_output():
    digest = pseudonymize("alice", "secret")
    assert "alice" not in digest
