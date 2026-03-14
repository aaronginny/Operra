import typing

def fix_webhook():
    with open('app/services/webhook_service.py', 'r', encoding='utf-8') as f:
        text = f.read()
        
    # We want to replace the process_incoming_message's task checking part
    new_text = text.replace(
        "extracted = await extract_task_from_message(text, known_employee_names=known_names)",
        """
    from app.services.ai_service import analyze_progress_update
    
    # Let's see if the employee has an active task and this is a progress update
    employee_for_update = None
    if sender != "unknown":
        employee_for_update = await get_employee_by_phone(db, sender)
        
    if employee_for_update:
        stmt = (
            select(Task)
            .where(
                Task.assigned_employee_id == employee_for_update.id,
                Task.status.in_([TaskStatus.pending, TaskStatus.in_progress]),
            )
            .order_by(Task.created_at.desc())
            .limit(1)
        )
        task_res = await db.execute(stmt)
        active_task = task_res.scalars().first()
        
        if active_task:
            analysis = await analyze_progress_update(text, active_task.title)
            if analysis.get("type") in ["progress_update", "task_completion"]:
                pct = analysis.get("progress_percent")
                if pct is not None:
                    active_task.progress_percent = pct
                
                active_task.last_update = datetime.now()
                active_task.status = TaskStatus.completed if analysis.get("type") == "task_completion" else TaskStatus.in_progress
                if active_task.status == TaskStatus.completed:
                    active_task.completed_at = datetime.now()
                elif active_task.status == TaskStatus.in_progress and not active_task.started_at:
                    active_task.started_at = datetime.now()
                    
                await db.flush()
                
                logger.info('Employee %s updated progress for "%s" to %s%%.', employee_for_update.name, active_task.title, pct)
                await send_whatsapp_message(sender, f"Progress updated: {pct}%. Keep it up!")
                
                return {
                    "status": "task_updated",
                    "employee": employee_for_update.name,
                    "task_id": active_task.id,
                    "task_title": active_task.title,
                    "new_status": active_task.status.value,
                    "message_log_id": log.id
                }

    extracted = await extract_task_from_message(text, known_employee_names=known_names)
"""
    )
    with open('app/services/webhook_service.py', 'w', encoding='utf-8') as f:
        f.write(new_text)

fix_webhook()
