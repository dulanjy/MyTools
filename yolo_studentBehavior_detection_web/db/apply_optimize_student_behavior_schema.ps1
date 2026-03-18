param(
    [string]$DbHost = "127.0.0.1",
    [int]$Port = 3306,
    [string]$Database = "student_behavior",
    [string]$User = "root",
    [string]$Password = "123456",
    [string]$MysqlCommand = "mysql"
)

$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "optimize_student_behavior_schema.sql"
if (-not (Test-Path $scriptPath)) {
    throw "SQL script not found: $scriptPath"
}

$env:MYSQL_PWD = $Password
try {
    Write-Host "[1/3] Applying schema optimization script..."
    & $MysqlCommand "-h$DbHost" "-P$Port" "-u$User" $Database "-e" "source $scriptPath"
    if ($LASTEXITCODE -ne 0) {
        throw "mysql returned non-zero exit code: $LASTEXITCODE"
    }

    Write-Host "[2/3] Verifying key indexes..."
    & $MysqlCommand "-h$DbHost" "-P$Port" "-u$User" $Database "-e" @"
SHOW INDEX FROM imgrecords;
SHOW INDEX FROM videorecords;
SHOW INDEX FROM camerarecords;
SHOW INDEX FROM student_behavior_records;
SHOW INDEX FROM user;
"@

    Write-Host "[3/3] Done."
}
finally {
    Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue
}
