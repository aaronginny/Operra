import os

file_path = "d:/Ops Ai Assistant/ai_ops_assistant/app/config.py"
with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

new_fields = '''    
    # ── Security ──────────────────────────────────────────────
    secret_key: str = "super_secret_dev_key_operra_123!"
    cors_origins: list[str] = ["*"]
    
    # ── Database ──────────────────────────────────────────────
'''

text = text.replace("    # ── Database ──────────────────────────────────────────────", new_fields)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(text)

print("Updated config.py")
