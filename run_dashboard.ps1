# Creates .venv next to this script (wherever the project lives), installs deps, runs the dashboard.
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}
& ".\.venv\Scripts\python.exe" -m pip install -q -r "services\dashboard\requirements.txt"
& ".\.venv\Scripts\python.exe" -m streamlit run "services\dashboard\app.py"
