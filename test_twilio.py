import asyncio, logging, sys
from app.services.messaging_service import send_whatsapp_message
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
async def test():
    await send_whatsapp_message('+919150016161', 'Test message from script')
asyncio.run(test())
