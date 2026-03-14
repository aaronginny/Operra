def fix_js():
    with open('app/static/index.html', 'r', encoding='utf-8') as f:
        text = f.read()

    text = text.replace('api("/tasks")', 'api("/tasks?company_id=1")')
    text = text.replace('api("/employees")', 'api("/employees?company_id=1")')
    text = text.replace('api("/analytics/employees")', 'api("/analytics/employees?company_id=1")')

    with open('app/static/index.html', 'w', encoding='utf-8') as f:
        f.write(text)
fix_js()
