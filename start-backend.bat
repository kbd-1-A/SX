@echo off
cd /d e:\时序\backend
uvicorn app.main:app --port 8000
pause