def fix_dashboard():
    with open('app/static/index.html', 'r', encoding='utf-8') as f:
        text = f.read()

    text = text.replace(
        "if (activeStatus && t.status !== activeStatus) return false;",
        "if (activeStatus && t.status !== activeStatus) return false;\n        if (!activeStatus && t.status === 'archived') return false;"
    )
    with open('app/static/index.html', 'w', encoding='utf-8') as f:
        f.write(text)
fix_dashboard()
