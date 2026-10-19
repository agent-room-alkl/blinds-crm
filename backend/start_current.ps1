# Canonical local app uses the configured PostgreSQL vera schema.
$env:VERA_DB_BACKEND='postgres'
$env:VERA_AUTO_INIT='0'
$env:VERA_STORAGE_BACKEND='local'
$env:VERA_EMAIL_MODE='demo'
# Preserve private SMTP settings from the environment/backend .env/root .env.
# email_service requires SMTP_FROM to match VERA_DEMO_EMAIL_ADDRESS in demo mode
# and forces every recipient to that address. Missing settings keep delivery off.
Set-Location $PSScriptRoot
python -m uvicorn service:app --host 127.0.0.1 --port 8002
