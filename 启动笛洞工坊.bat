@echo off
rem 优先用写死的 Python（本机路径）；换机器时不存在就退回 PATH 里的 python
set "MIUSICV_PY=G:\Conda\python.exe"
if not exist "%MIUSICV_PY%" set "MIUSICV_PY=python"
"%MIUSICV_PY%" "%~dp0editor.py"
