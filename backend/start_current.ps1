# Canonical local app uses the configured PostgreSQL vera schema.
$env:VERA_DB_BACKEND='postgres'
$env:VERA_AUTO_INIT='0'
$env:VERA_STORAGE_BACKEND='local'
$env:SMTP_HOST=''
$env:SMTP_FROM=''
$env:SMTP_USERNAME=''
$env:SMTP_PASSWORD=''
Set-Location $PSScriptRoot
python -m uvicorn service:app --host 127.0.0.1 --port 8002
