from app.encryption import decrypt, encrypt


def test_roundtrip_short_string():
    original = "sk-abc123"
    assert decrypt(encrypt(original)) == original


def test_roundtrip_long_string():
    original = "sk-" + "x" * 200
    assert decrypt(encrypt(original)) == original


def test_roundtrip_unicode():
    original = "key-with-ünïcödé-chars"
    assert decrypt(encrypt(original)) == original


def test_ciphertext_differs_from_plaintext():
    original = "sk-secret"
    encrypted = encrypt(original)
    assert encrypted != original


def test_different_encryptions_produce_different_ciphertext():
    original = "sk-secret"
    enc1 = encrypt(original)
    enc2 = encrypt(original)
    assert enc1 != enc2
    assert decrypt(enc1) == decrypt(enc2) == original
