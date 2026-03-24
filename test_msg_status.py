import asyncio, logging, sys
from twilio.rest import Client
from app.config import settings
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
def check():
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    msgs = client.messages.list(limit=5)
    for m in msgs:
        print(f'To: {m.to}, Status: {m.status}, Error Message: {m.error_message}, Error Code: {m.error_code}')
check()
