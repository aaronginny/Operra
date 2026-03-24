import asyncio, aiosqlite
async def get_tasks():
    async with aiosqlite.connect('ai_ops_v2.db') as db:
        async with db.execute('SELECT id, title, assigned_employee_id, notification_sent FROM tasks') as cursor:
            rows = await cursor.fetchall()
            for r in rows: print(r)
asyncio.run(get_tasks())
