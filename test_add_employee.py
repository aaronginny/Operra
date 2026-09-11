import os

# This file, unlike every other test_*.py here, runs against whatever
# DATABASE_URL .env points at (the real local dev DB) rather than an
# isolated throwaway one — a pre-existing gap, unrelated to this pin, that
# is why it currently fails on a stale local schema (missing columns added
# by later migrations) rather than on anything below.
#
# It DOES send messages like "Ryan pack 5 boxes by 6pm" through
# process_incoming_message, which routes to ai_service.py's OpenAI-guarded
# extraction. That must stay on the rule-based fallback regardless of what
# real key sits in the local .env (kept there for broker_intel's live-
# verification probes) or this file silently starts making live OpenAI
# calls once the schema issue above is fixed.
os.environ["OPENAI_API_KEY"] = "sk-your-openai-api-key-here"

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session
from app.services.webhook_service import process_incoming_message
from app.models.employee import Employee
from app.models.task import Task
from sqlalchemy import select

async def run_test():
    async with async_session() as session:
        # Test 1: Add Ryan with country code
        print("-" * 50)
        print("Testing: ADD Ryan +919384676233")
        res1 = await process_incoming_message(session, "+919999999999", "ADD Ryan +919384676233")
        print("Result 1:", res1)
        
        # Verify db
        stmt = select(Employee).where(Employee.phone_number == "+919384676233")
        ryan = (await session.execute(stmt)).scalars().first()
        print(f"DB Verification 1: Found Ryan? {ryan is not None}. Name={getattr(ryan, 'name', None)}")

        # Test 2: Add Ryan without country code (should normalize to +91 and return already exists)
        print("-" * 50)
        print("Testing: add ryan 9384676233")
        res2 = await process_incoming_message(session, "+919999999999", "add ryan 9384676233")
        print("Result 2:", res2)

        # Test 3: Assign a task to Ryan
        print("-" * 50)
        print("Testing task assignment: Ryan pack 5 boxes by 6pm")
        res3 = await process_incoming_message(session, "+919999999999", "Ryan pack 5 boxes by 6pm")
        print("Result 3:", res3)

        # Verify task creation
        stmt2 = select(Task).where(Task.assigned_employee_id == (ryan.id if ryan else -1))
        task = (await session.execute(stmt2)).scalars().first()
        print(f"DB Verification 3: Found Task? {task is not None}. Title={getattr(task, 'title', None)}, Assigned To={getattr(task, 'assigned_to', None)}")

        await session.commit()

if __name__ == "__main__":
    asyncio.run(run_test())
