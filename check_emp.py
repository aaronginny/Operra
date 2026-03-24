import asyncio, aiosqlite
async def get_employees():
    async with aiosqlite.connect('ai_ops_v2.db') as db:
        async with db.execute('SELECT id, name, phone_number FROM employees') as cursor:
            rows = await cursor.fetchall()
            for r in rows: print(r)
asyncio.run(get_employees())
