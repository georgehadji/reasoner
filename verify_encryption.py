import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from reasoner.security.encryption import EncryptionService


def test_encryption():
    # Setup a test key
    key = EncryptionService.generate_key()
    service = EncryptionService(keys=[key])

    plaintext = "Sensitive data 123"
    print(f"Plaintext: {plaintext}")

    ciphertext = service.encrypt(plaintext)
    print(f"Ciphertext: {ciphertext}")

    # Ensure it's different
    assert plaintext != ciphertext

    decrypted = service.decrypt(ciphertext)
    print(f"Decrypted: {decrypted}")

    assert plaintext == decrypted
    print("Encryption/Decryption test passed!")

if __name__ == "__main__":
    try:
        test_encryption()
    except Exception as e:
        print(f"Test failed: {e}")
        sys.exit(1)
