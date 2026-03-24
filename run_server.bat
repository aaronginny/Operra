@echo off
echo Login system ready at http://127.0.0.1:8000/login
call .venv\Scripts\activate.bat
uvicorn app.main:app --reload
