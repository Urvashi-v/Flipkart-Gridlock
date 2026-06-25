# demo_up.ps1 — bring up EVERYTHING for the judges with one command.
#   Right-click > Run with PowerShell,  or:   powershell -ExecutionPolicy Bypass -File demo_up.ps1
#
# Launches the API+Dashboard server and Streamlit app, then opens all surfaces.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "`n  Gridlock - starting demo surfaces...`n" -ForegroundColor Red

# 1. API + Dashboard (single server)  -> http://localhost:8000
Start-Process powershell -ArgumentList @(
  "-NoExit", "-Command",
  "Set-Location '$PSScriptRoot'; Write-Host 'API + DASHBOARD SERVER - keep open' -ForegroundColor Green; python -m uvicorn api:app --port 8000"
)

# 2. Streamlit live app  -> http://localhost:8501
Start-Process powershell -ArgumentList @(
  "-NoExit", "-Command",
  "Set-Location '$PSScriptRoot'; Write-Host 'STREAMLIT APP - keep open' -ForegroundColor Green; streamlit run app.py"
)

# 3. Give the servers a moment, then open surfaces
Start-Sleep -Seconds 7
Start-Process "http://localhost:8000"                              # Dashboard (LEAD WITH THIS)
Start-Process "http://localhost:8000/congestion_command.html"      # Live command centre
Invoke-Item ".\outputs\briefing_pack.pdf"                          # Field briefings
Invoke-Item ".\outputs\daily_digest.md"                            # Daily ops digest

Start-Sleep -Seconds 5
Start-Process "http://localhost:8501"                              # Streamlit app
Start-Process "http://localhost:8000/docs"                         # API docs

Write-Host "`n  Up:  dashboard(:8000), command-centre, streamlit(:8501), API docs(:8000/docs)" -ForegroundColor Cyan
Write-Host "  No login needed - open access to all features." -ForegroundColor Yellow
Write-Host "  Close the two server windows (Ctrl+C) when the demo is done.`n" -ForegroundColor DarkGray
