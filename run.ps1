Set-Location $PSScriptRoot
.\.venv\Scripts\python -m uvicorn main:app --reload
