import os

path = r'D:\Ops Ai Assistant\ai_ops_assistant\app\main.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

if 'from app.config import settings' not in text:
    text = 'from app.config import settings\n' + text
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    print('Added import to main.py')
else:
    print('Import already there')
