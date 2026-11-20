@echo off
cd /d "%~dp0"
py -3 -m focus_shield.main
if errorlevel 1 (
  echo Pianissimo could not start. Install the dependencies described in README.md.
  pause
)
