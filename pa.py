def fix_analytics():
    with open('app/services/analytics_service.py', 'r', encoding='utf-8') as f:
        text = f.read()

    text = text.replace(
        "async def get_employee_performance(db: AsyncSession) -> list[dict]:",
        "async def get_employee_performance(db: AsyncSession, company_id: int | None = None) -> list[dict]:"
    )

    text = text.replace(
        ".where(Task.assigned_employee_id.isnot(None))",
        ".where(Task.assigned_employee_id.isnot(None))\n    if company_id is not None:\n        stmt = stmt.where(Task.company_id == company_id)"
    )
    with open('app/services/analytics_service.py', 'w', encoding='utf-8') as f:
        f.write(text)
fix_analytics()
