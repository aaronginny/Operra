def fix_analytics_route():
    with open('app/routes/analytics.py', 'r', encoding='utf-8') as f:
        text = f.read()

    text = text.replace(
        "async def employee_performance(db: AsyncSession = Depends(get_db)):",
        "from fastapi import Query\nasync def employee_performance(company_id: int | None = Query(None), db: AsyncSession = Depends(get_db)):"
    )

    text = text.replace(
        "return await get_employee_performance(db)",
        "return await get_employee_performance(db, company_id=company_id)"
    )
    with open('app/routes/analytics.py', 'w', encoding='utf-8') as f:
        f.write(text)
fix_analytics_route()
