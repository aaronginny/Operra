import os

file_path = "d:/Ops Ai Assistant/ai_ops_assistant/app/main.py"
with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

text = text.replace("allow_origins=[\"*\"],", "allow_origins=settings.cors_origins,")
text = text.replace("from app.config", "from app.config import settings\nfrom app.config")

# remove dup if there is one
text = text.replace("from app.config import settings\nfrom app.config", "from app.config import settings")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(text)

print("Updated main.py")
