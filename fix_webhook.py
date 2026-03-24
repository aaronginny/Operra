import os
import re

file_path = "d:/Ops Ai Assistant/ai_ops_assistant/app/services/webhook_service.py"
with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

# Replace process_incoming_message definition to remove company_id: int = 1
new_sig = '''async def process_incoming_message(
    db: AsyncSession,
    sender: str,
    text: str,
    force_company_id: int = None,
) -> dict:'''

text = text.replace('''async def process_incoming_message(
    db: AsyncSession,
    sender: str,
    text: str,
    company_id: int = 1,
) -> dict:''', new_sig)

# Add logic to find company_id
logic_old = '''
    if not text.strip():
        return {"status": "no_text"}

    # ── Auto-register employee if first contact ──────────────────
'''

logic_new = '''
    if not text.strip():
        return {"status": "no_text"}
        
    # resolve company_id from sender
    # First, try to find an employee with this phone
    existing_emp = await get_employee_by_phone(db, sender)
    
    if existing_emp:
        company_id = existing_emp.company_id
    elif force_company_id is not None:
        company_id = force_company_id
    else:
        # Fallback to the first company (admin company) if unknown
        # In a real SaaS, we might reject the message or put in a 'ghost' company
        company_id = 1

    # ── Auto-register employee if first contact ──────────────────
'''

text = text.replace(logic_old, logic_new)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(text)

print("Updated webhook_service.py")
