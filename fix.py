import re

with open('app/services/ai_service.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace(r'f\"\"\"', 'f\"\"\"')

with open('app/services/ai_service.py', 'w', encoding='utf-8') as f:
    f.write(text)
