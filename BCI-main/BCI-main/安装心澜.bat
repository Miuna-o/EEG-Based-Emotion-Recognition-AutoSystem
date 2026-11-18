@echo off
title Xinlan Setup
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" -LegacyCertificates
if errorlevel 1 pause
