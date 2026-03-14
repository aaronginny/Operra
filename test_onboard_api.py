import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session
from app.models.employee import Employee
from app.models.task import Task
from sqlalchemy import select
from fastapi.testclient import TestClient
from app.main import app

def run_test():
    client = TestClient(app)
    print("-" * 50)
    print("Testing: POST /api/dashboard/onboard-assign")
    payload = {
        "company_id": 1,
        "employee_name": "Test CEO Hire",
        "phone_number": "+919999999998",
        "title": "Pack 50 boxes by EOD",
    }
    response = client.post("/api/dashboard/onboard-assign", json=payload)
    print("Status Code:", response.status_code)
    print("Response:", response.json())

async def verify_db():
    # Verify DB directly
    async with async_session() as session:
        stmt = select(Employee).where(Employee.phone_number == "+919999999998")
        emp = (await session.execute(stmt)).scalars().first()
        print(f"DB Verification - Found Employee? {emp is not None}. Name={getattr(emp, 'name', None)}")

        if emp:
            stmt2 = select(Task).where(Task.assigned_employee_id == emp.id)
            task = (await session.execute(stmt2)).scalars().first()
            print(f"DB Verification - Found Task? {task is not None}. Title={getattr(task, 'title', None)}, Assigned To={getattr(task, 'assigned_to', None)}")

if __name__ == "__main__":
    run_test()
    asyncio.run(verify_db())
