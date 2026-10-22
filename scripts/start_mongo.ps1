param([int]$Port = 27017)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskMongo = Get-Command mongod -ErrorAction SilentlyContinue
if (-not $taskMongo) {
    throw 'mongod was not found. Install MongoDB Community Server and add its bin directory to PATH.'
}
$taskData = Join-Path $taskRoot 'work\mongodb\data'
$taskLog = Join-Path $taskRoot 'work\mongodb\mongod.log'
New-Item -ItemType Directory -Force -Path $taskData | Out-Null
Write-Host "MongoDB: 127.0.0.1:$Port; data: $taskData"
Write-Host 'Keep this terminal open. Press Ctrl+C to stop MongoDB.'
& $taskMongo.Source --dbpath $taskData --logpath $taskLog --logappend --bind_ip 127.0.0.1 --port $Port
if ($LASTEXITCODE -ne 0) {
    throw "MongoDB exited with code $LASTEXITCODE. See $taskLog"
}
