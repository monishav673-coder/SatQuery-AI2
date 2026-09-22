"""
Generate cryptographically strong secret keys for SATQUERY AI .env.
Run: python scripts/generate_secret_key.py
"""
import secrets

print("=" * 60)
print("  SATQUERY AI — Secret Key Generator")
print("=" * 60)
print(f"\nSECRET_KEY={secrets.token_hex(32)}")
print(f"JWT_SECRET_KEY={secrets.token_hex(32)}")
print(f"\nCopy the above into your .env file.")
print("NEVER commit .env to version control.\n")
