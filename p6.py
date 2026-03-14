def fix_128():
    with open('app/services/reminder_service.py', 'r', encoding='utf-8') as f:
        text = f.read()

    text = text.replace(
        "await send_whatsapp_message(emp.phone_number, \"Daily Update\n\nWhat progress did you make today?\")",
        "await send_whatsapp_message(emp.phone_number, \"Daily Update\\n\\nWhat progress did you make today?\")"
    )
    with open('app/services/reminder_service.py', 'w', encoding='utf-8') as f:
        f.write(text)
fix_128()
