@echo off
title Xinlan Diagnostics
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\diagnose.ps1"
pause
