try:
    import email_validator
    print(f"email-validator installed: {email_validator.__version__}")
except ImportError as e:
    print(f"NOT installed: {e}")

try:
    from pydantic import EmailStr
    print("EmailStr import OK")
except ImportError as e:
    print(f"EmailStr import failed: {e}")
