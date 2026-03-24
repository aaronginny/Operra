try:
    from app.main import app
    print(f"App loaded successfully: {app.title}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
