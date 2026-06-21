# demo_up.ps1 — bring up EVERYTHING for the judges with one command.
#   Right-click > Run with PowerShell,  or:   powershell -ExecutionPolicy Bypass -File demo_up.ps1
#
# Launches the Streamlit app + REST API in their own windows and opens the
# dashboard, briefing PDF, daily digest, and interactive map in your browser.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "`n  Gridlock — starting demo surfaces...`n" -ForegroundColor Red

# 1. Streamlit live app  -> http://localhost:8501
Start-Process powershell -ArgumentList @(
  "-NoExit", "-Command",
  "Set-Location '$PSScriptRoot'; Write-Host 'STREAMLIT APP - keep open' -ForegroundColor Green; streamlit run app.py"
)

# 2. REST API  -> http://localhost:8000/docs
Start-Process powershell -ArgumentList @(
  "-NoExit", "-Command",
  "Set-Location '$PSScriptRoot'; Write-Host 'REST API - keep open' -ForegroundColor Green; python -m uvicorn api:app --port 8000"
)

# 3. Static server for the portal/command-centre/console (they need HTTP, not file://)
Start-Process powershell -ArgumentList @(
  "-NoExit", "-Command",
  "Set-Location '$PSScriptRoot'; Write-Host 'STATIC SERVER (outputs) - keep open' -ForegroundColor Green; python -m http.server 8540 --directory outputs"
)

# 4. give the servers a moment, then open the surfaces over HTTP
Start-Sleep -Seconds 7
Start-Process "http://localhost:8540/portal.html"            # LOGIN page -> opens the role dashboard (LEAD WITH THIS)
Start-Process "http://localhost:8540/congestion_command.html" # live command centre
Invoke-Item ".\outputs\briefing_pack.pdf"                   # field briefings
Invoke-Item ".\outputs\daily_digest.md"                     # daily ops digest

Start-Sleep -Seconds 6
Start-Process "http://localhost:8501"                        # Streamlit app
Start-Process "http://localhost:8000/docs"                  # API docs

Write-Host "`n  Up:  portal(:8540/portal.html), command-centre, app(:8501), API(:8000/docs)" -ForegroundColor Cyan
Write-Host "  Login -> admin: admin / admin@gridlock   |   viewer: viewer / viewer@gridlock" -ForegroundColor Yellow
Write-Host "  Close the three server windows (Ctrl+C) when the demo is done.`n" -ForegroundColor DarkGray
