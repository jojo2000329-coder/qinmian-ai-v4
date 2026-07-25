$ErrorActionPreference = "Continue"
Set-Location -LiteralPath $PSScriptRoot
$python = "C:\Users\KyawNaing\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$app = Join-Path -Path $PSScriptRoot -ChildPath "app.py"

Write-Host ""
Write-Host "Qinmian is running at http://127.0.0.1:8765/"
Write-Host "Keep this PowerShell window open. Press Ctrl+C to stop."
Write-Host ""

& $python $app 8765
