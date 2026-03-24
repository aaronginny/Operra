# add_logout.py
import sys

with open('app/static/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

logout_btn = '<button class="btn btn-sm btn-ghost" onclick="localStorage.removeItem(\'token\'); window.location.href=\'/dashboard/\'">Logout</button>'
content = content.replace('<div class="header-user">', '<div class="header-user">\n            ' + logout_btn)

with open('app/static/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)
