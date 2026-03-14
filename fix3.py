def fix_reminder():
    with open('app/services/reminder_service.py', 'r', encoding='utf-8') as f:
        text = f.read()

    # Track _last_checkin_date
    text = text.replace(
        "_scheduler_task: asyncio.Task | None = None",
        "_scheduler_task: asyncio.Task | None = None\n_last_checkin_date = None"
    )

    # In _check_and_remind
    # we add logic for interval reminders and the daily check-in bot.
    # The simplest is to put daily check-in check at the end.
    
    new_loop_logic = '''        for task in tasks:
            if task.due_at is None:
                pass
            else:
                due = task.due_at.replace(tzinfo=None) if task.due_at.tzinfo else task.due_at
                employee = task.assigned_employee
                assignee_name = employee.name if employee else (task.assigned_to or "Team")
                assignee_phone = (employee.phone_number if employee else None) or "unknown"
                assignee_email = employee.email if employee else None

                time_left = due - now
                deadline_str = due.strftime("%I:%M %p").lstrip("0")

                # Tier 0: Overdue
                if due < now:
                    task.status = TaskStatus.overdue
                    msg = format_deadline_alert(task.title)
                    await send_whatsapp_message(assignee_phone, msg)
                    if assignee_email:
                        await send_email(assignee_email, msg)
                    logger.info("Marked task #%s as overdue.", task.id)
                    continue

                if time_left <= URGENT_WINDOW:
                    if _cooldown_ok(task.last_urgent_reminder_sent, now):
                        msg = format_urgent_reminder(task.title)
                        await send_whatsapp_message(assignee_phone, msg)
                        if assignee_email:
                            await send_email(assignee_email, msg)
                        task.last_urgent_reminder_sent = now
                    continue

                if time_left <= FOLLOWUP_WINDOW:
                    if _cooldown_ok(task.last_followup_sent, now):
                        msg = format_progress_check(assignee_name, task.title, deadline_str)
                        await send_whatsapp_message(assignee_phone, msg)
                        if assignee_email:
                            await send_email(assignee_email, msg)
                        task.last_followup_sent = now

            # FEATURE 3 -> interval reminders
            if task.reminder_interval_days:
                last_up = task.last_update or task.created_at
                last_up_naive = last_up.replace(tzinfo=None) if last_up.tzinfo else last_up
                if (now - last_up_naive).days >= task.reminder_interval_days:
                    # check if we already nudged them recently
                    if _cooldown_ok(task.last_followup_sent, now):
                        employee = task.assigned_employee
                        assignee_phone = (employee.phone_number if employee else None) or "unknown"
                        msg = f"Interval Reminder\n\nDon\'t forget your task: {task.title}"
                        await send_whatsapp_message(assignee_phone, msg)
                        task.last_update = now # reset interval
                        task.last_followup_sent = now

        # FEATURE 5 -> Daily check-in bot
        global _last_checkin_date
        today = now.date()
        # let's say we send it at 9 AM or whenever, or just once a day if now.hour >= 9
        if getattr(settings, 'checkin_bot_enabled', True):
            if now.hour >= 9 and _last_checkin_date != today:
                # get all employees with active tasks
                stmt_emp = select(Task.assigned_employee_id).where(Task.status.in_([TaskStatus.pending, TaskStatus.in_progress])).distinct()
                emp_res = await db.execute(stmt_emp)
                emp_ids = emp_res.scalars().all()
                for eid in emp_ids:
                    if eid:
                        from app.models.employee import Employee
                        emp = await db.get(Employee, eid)
                        if emp and emp.phone_number:
                            await send_whatsapp_message(emp.phone_number, "Daily Update\\n\\nWhat progress did you make today?")
                _last_checkin_date = today

        await db.commit()'''

    import re
    # We replace from "for task in tasks:" to "await db.commit()" entirely
    text = re.sub(r"        for task in tasks:.*        await db.commit()", new_loop_logic, text, flags=re.DOTALL)
    
    with open('app/services/reminder_service.py', 'w', encoding='utf-8') as f:
        f.write(text)

fix_reminder()
