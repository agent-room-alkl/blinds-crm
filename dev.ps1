param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('backend','frontend')]
    [string]$Service
)

# Run each service in its own terminal. Ctrl+C stops that service.
$ErrorActionPreference='Stop'
if ($Service -eq 'backend') {
    Push-Location (Join-Path $PSScriptRoot 'backend')
    try {
        & python -m uvicorn app.main:app --host 127.0.0.1 --port 8002
    } finally { Pop-Location }
} else {
    $taskPreviousApi=$env:VERA_DEV_API_URL
    $env:VERA_DEV_API_URL='http://127.0.0.1:8002'
    Push-Location (Join-Path $PSScriptRoot 'frontend')
    try {
        & npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
    } finally {
        Pop-Location
        $env:VERA_DEV_API_URL=$taskPreviousApi
    }
}
