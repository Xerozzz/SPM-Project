"""Password hashing. bcrypt's 72-byte limit is enforced here, not left to the library."""

import pytest

from core.security import hash_password, verify_password

# Exactly at the limit: the longest password bcrypt hashes in full.
_AT_LIMIT = "a" * 72


@pytest.mark.story("SCRUM-27")
def test_a_password_at_the_bcrypt_limit_round_trips() -> None:
    assert verify_password(_AT_LIMIT, hash_password(_AT_LIMIT))


@pytest.mark.story("SCRUM-27")
def test_a_password_sharing_the_first_72_bytes_with_the_real_one_is_wrong() -> None:
    # The finding from PR #4 review: bcrypt 4.x truncates instead of raising, so without an
    # explicit length check this longer password would verify against the shorter one's hash.
    assert not verify_password(_AT_LIMIT + "extra", hash_password(_AT_LIMIT))


@pytest.mark.story("SCRUM-27")
def test_the_limit_is_measured_in_utf8_bytes_not_characters() -> None:
    # 36 two-byte characters is 72 bytes — fine. One more crosses the limit at 37 chars.
    two_byte = "é" * 36
    assert verify_password(two_byte, hash_password(two_byte))
    assert not verify_password(two_byte + "é", hash_password(two_byte))


@pytest.mark.story("SCRUM-27")
def test_hashing_refuses_a_password_bcrypt_would_truncate() -> None:
    # Storing a silently truncated hash would be worse than failing loudly at seed time.
    with pytest.raises(ValueError, match="72-byte"):
        hash_password(_AT_LIMIT + "extra")
