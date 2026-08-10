from shared.security.hashing import hash_password,verify_password

def test_hash_is_not_the_plaintext():
    hashed = hash_password("correct-horse-battery-staple")
    assert hashed != "correct-horse-battery-staple"

def test_verify_accepts_correct_password():
    hashed=hash_password("correct-horse-battery-staple")
    assert verify_password("correct-horse-battery-staple",hashed) is True

def test_verify_rejects_wrong_password():
    hashed=hash_password("correct-horse-battery-staple")
    assert verify_password("wrong-password",hashed) is False

def test_same_password_hashes_differently_each_time():
    #bcrypt salts each hash - this guards against some accidentally
    # swapping in a non-salted scheme later
    first=hash_password("same-password")
    second=hash_password("same-password")
    assert first != second