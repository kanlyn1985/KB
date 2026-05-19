$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $workspaceRoot

$hostAddress = "127.0.0.1"
$port = 8000
$url = "http://${hostAddress}:${port}/demo"

Write-Host ""
Write-Host "Enterprise Agent KB"
Write-Host "Workspace: $workspaceRoot"
Write-Host ""
Write-Host "Starting HTTP API and demo..."
Write-Host "Demo URL: $url"
Write-Host ""
Write-Host "Other useful endpoints:"
Write-Host "  Health: http://${hostAddress}:${port}/health"
Write-Host "  MCP:    python -m enterprise_agent_kb.cli --root knowledge_base serve-mcp"
Write-Host ""
Write-Host "Fast tests:        pytest -q"
Write-Host "Benchmark tests:   pytest -q -m benchmark"
Write-Host "Integration tests: pytest -q -m integration"
Write-Host ""

Start-Process $url | Out-Null
python -m enterprise_agent_kb.cli --root knowledge_base serve-api --host $hostAddress --port $port

