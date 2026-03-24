# fix_dash.py
import sys

with open('app/static/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    'headers: { "Content-Type": "application/json" },',
    'headers: { "Content-Type": "application/json", "Authorization": "Bearer " + localStorage.getItem("token") },'
)
content = content.replace(
    'const API = window.location.origin;',
    'const API = window.location.origin;\n      if (!localStorage.getItem("token")) window.location.href = "/dashboard/login.html";'
)
content = content.replace('?company_id=1', '')

with open('app/static/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)
