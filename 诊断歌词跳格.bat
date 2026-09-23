@echo off

set MIUSICV_IME_DEBUG=1
if exist "%~dp0tests\_ime_debug.log" del "%~dp0tests\_ime_debug.log"
set "MIUSICV_PY=G:\Conda\python.exe"
if not exist "%MIUSICV_PY%" set "MIUSICV_PY=python"
"%MIUSICV_PY%" "%~dp0editor.py"
if exist "%~dp0tests\_ime_debug.log" (
  notepad "%~dp0tests\_ime_debug.log"
) else (
  echo No log was produced.
  pause
)
