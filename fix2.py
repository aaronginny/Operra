def fix_ai_service():
    with open('app/services/ai_service.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # We will just rewrite the bottom part. Let's find the def analyze_progress_update(text: str, task_title: str) -> dict: line
    for i, line in enumerate(lines):
        if "async def analyze_progress_update" in line:
            out_lines = lines[:i]
            break
            
    code = '''async def analyze_progress_update(text: str, task_title: str) -> dict:
    if not settings.openai_api_key or settings.openai_api_key.startswith("sk-your"):
        text_lower = text.lower()
        if "done" in text_lower or "completed" in text_lower:
            return {"type": "task_completion", "progress_percent": 100}
        elif "%" in text_lower:
            return {"type": "progress_update", "progress_percent": 50}
        return {"type": "no_progress", "progress_percent": None}

    sys_prompt = f"""You are analyzing an employee's progress update for the task: '{task_title}'.
Parse the message and return ONLY valid JSON with keys:
  "type": one of ["progress_update", "task_completion", "no_progress"]
  "progress_percent": an integer from 0 to 100, or null if no progress or completion
"""
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": text},
        ],
        "temperature": 0.0,
    }
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
    try:
        j = json.loads(response.json()["choices"][0]["message"]["content"])
        return j
    except:
        return {"type": "no_progress", "progress_percent": None}
'''
    with open('app/services/ai_service.py', 'w', encoding='utf-8') as f:
        f.writelines(out_lines)
        f.write(code)

fix_ai_service()
