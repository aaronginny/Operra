import json
from app.config import settings
import httpx
import re

async def analyze_progress_update(text: str, task_title: str) -> dict:        
    if not settings.openai_api_key or settings.openai_api_key.startswith("sk-your"):
        text_lower = text.lower()
        if "done" in text_lower or "completed" in text_lower:
            return {"type": "task_completion", "progress_percent": 100}
        
        # Rule based fallback for UPDATE <progress>
        match = re.search(r"update\s+(\d+)", text_lower)
        if match:
            return {"type": "progress_update", "progress_percent": int(match.group(1))}
        return {"type": "no_progress", "progress_percent": None}

    sys_prompt = f\"\"\"You are analyzing an employee's progress update for the task: '{task_title}'.
Parse the message and return ONLY valid JSON with keys:
  "type": one of ["progress_update", "task_completion", "no_progress"]
  "progress_percent": an integer from 0 to 100, or null if no progress or completion
\"\"\"
    payload = {
        "model": getattr(settings, 'openai_model', 'gpt-4o-mini'),
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": text},
        ],
        "temperature": 0.0,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        
        j = json.loads(response.json()["choices"][0]["message"]["content"])     
        return j
    except Exception:
        return {"type": "no_progress", "progress_percent": None}
