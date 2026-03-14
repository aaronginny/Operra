# Operra
**AI Operations Assistant for Teams**

Backend API that captures WhatsApp messages, extracts tasks via AI, tracks them, and sends reminders through WhatsApp and email.

## Quick Start

```bash
# 1. Create a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
copy .env.example .env        # then edit .env with your credentials

# 4. Run the application
uvicorn app.main:app --reload
```

The API docs are available at **http://127.0.0.1:8000/docs** (Swagger UI).

## Environment Variables

Copy `.env.example` → `.env` and fill in your values:

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL async connection string |
| `OPENAI_API_KEY` | No | OpenAI key for AI task extraction (falls back to rule-based parser) |
| `OPENAI_MODEL` | No | OpenAI model name (default: `gpt-4o-mini`) |
| `WHATSAPP_VERIFY_TOKEN` | Yes | Token for WhatsApp webhook verification |
| `TWILIO_ACCOUNT_SID` | No* | Twilio Account SID for WhatsApp messaging |
| `TWILIO_AUTH_TOKEN` | No* | Twilio Auth Token |
| `TWILIO_WHATSAPP_NUMBER` | No* | Twilio sandbox or approved WhatsApp number (e.g. `+14155238886`) |
| `EMAIL_HOST` | No* | SMTP server hostname (default: `smtp.gmail.com`) |
| `EMAIL_PORT` | No* | SMTP port (default: `587`) |
| `EMAIL_USER` | No* | Sender email address |
| `EMAIL_PASSWORD` | No* | Email password or [Gmail App Password](https://support.google.com/accounts/answer/185833) |

> **\*Messaging fallback:** If Twilio or email credentials are not set, reminders are logged to the console instead — the app still runs normally.

### Gmail App Password

Gmail requires an **App Password** instead of your normal password when 2FA is enabled:

1. Go to [Google Account → Security → App Passwords](https://myaccount.google.com/apppasswords)
2. Generate a new app password for "Mail"
3. Use the generated 16-character password as `EMAIL_PASSWORD`

### Twilio WhatsApp Sandbox

For development, use the [Twilio WhatsApp Sandbox](https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn):

1. Create a free Twilio account
2. Activate the WhatsApp sandbox
3. Use the sandbox number as `TWILIO_WHATSAPP_NUMBER`
4. Have recipients join the sandbox by sending the join code from their phone
