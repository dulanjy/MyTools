[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Flask', 'Spring', 'Vite', 'Stop', 'Health')]
    [string]$Service
)

$ErrorActionPreference = 'Stop'

function Resolve-ProjectRoot {
    $workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

    if (Test-Path (Join-Path $workspaceRoot 'yolo_studentBehavior_detection_flask')) {
        return $workspaceRoot
    }

    $nestedRoot = Join-Path $workspaceRoot 'yolo_studentBehavior_detection_web'
    if (Test-Path (Join-Path $nestedRoot 'yolo_studentBehavior_detection_flask')) {
        return $nestedRoot
    }

    throw "Cannot locate project root from workspace: $workspaceRoot"
}

function Get-ListeningPidsMap {
    param([int[]]$Ports)

    $map = @{}
    foreach ($port in $Ports) {
        $map[$port] = @()
    }

    if ($Ports.Count -eq 0) {
        return $map
    }

    $regex = ':(' + (($Ports | Sort-Object -Unique) -join '|') + ')\s'
    $rows = netstat -ano -p tcp | Select-String $regex

    foreach ($row in $rows) {
        $line = ($row.ToString() -replace '^\s+', '')
        $parts = ($line -split '\s+') | Where-Object { $_ -ne '' }

        if ($parts.Length -lt 5) { continue }
        if ($parts[3] -ne 'LISTENING') { continue }
        if ($parts[1] -notmatch ':(\d+)$') { continue }

        $port = [int]$Matches[1]
        if (-not $map.ContainsKey($port)) { continue }

        $procId = 0
        if (-not [int]::TryParse($parts[4], [ref]$procId)) { continue }
        if ($procId -le 0) { continue }
        if ($map[$port] -contains $procId) { continue }

        $map[$port] += $procId
    }

    return $map
}

function Get-ProcessNameById {
    param([int]$ProcId)

    $proc = Get-Process -Id $ProcId -ErrorAction SilentlyContinue
    if ($null -eq $proc) { return 'unknown' }
    return $proc.ProcessName.ToLower()
}

function Has-Listener {
    param([hashtable]$Map)

    foreach ($entry in $Map.GetEnumerator()) {
        if ($entry.Value.Count -gt 0) {
            return $true
        }
    }

    return $false
}

function Get-BadOwners {
    param(
        [hashtable]$Map,
        [string[]]$ExpectedNames
    )

    $bad = @()
    foreach ($entry in $Map.GetEnumerator()) {
        $port = [int]$entry.Key
        foreach ($procId in $entry.Value) {
            $name = Get-ProcessNameById -ProcId $procId
            if ($ExpectedNames -contains $name) { continue }
            $bad += ($port.ToString() + '/' + $procId.ToString() + ':' + $name)
        }
    }

    return $bad
}

function Resolve-Python {
    param([string]$FlaskDir)

    $candidates = @()
    if ($env:YOLO_PYTHON) {
        $candidates += $env:YOLO_PYTHON
    }

    # Project policy: Flask must run with yolov8 environment python.
    $candidates += @(
        'C:\Users\hp1\anaconda3\envs\yolov8\python.exe',
        'C:\Users\hp1\miniconda3\envs\yolov8\python.exe'
    )

    # Try discovering yolov8 env path from conda metadata.
    $condaExeCandidates = @()
    if ($env:CONDA_EXE) {
        $condaExeCandidates += $env:CONDA_EXE
    }
    $condaExeCandidates += @(
        'C:\Users\hp1\anaconda3\Scripts\conda.exe',
        'C:\Users\hp1\miniconda3\Scripts\conda.exe'
    )

    foreach ($condaExe in ($condaExeCandidates | Select-Object -Unique)) {
        try {
            if (-not (Test-Path $condaExe)) { continue }
            $jsonRaw = & $condaExe env list --json 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $jsonRaw) { continue }

            $obj = $jsonRaw | ConvertFrom-Json
            foreach ($envPath in @($obj.envs)) {
                if (-not $envPath) { continue }
                if ((Split-Path $envPath -Leaf).ToLower() -ne 'yolov8') { continue }
                $pyPath = Join-Path $envPath 'python.exe'
                if (Test-Path $pyPath) {
                    $candidates += $pyPath
                }
            }
        }
        catch {
            continue
        }
    }

    $env:YOLO_CONFIG_DIR = Join-Path $FlaskDir '.ultralytics'
    if (-not (Test-Path $env:YOLO_CONFIG_DIR)) {
        New-Item -ItemType Directory -Path $env:YOLO_CONFIG_DIR -Force | Out-Null
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        try {
            if (-not (Test-Path $candidate)) { continue }
            if ($candidate.ToLower() -notmatch 'yolov8') { continue }
            return $candidate
        }
        catch {
            continue
        }
    }

    return $null
}

function Start-Flask {
    param([string]$FlaskDir)

    $ports = @(5000)
    $map = Get-ListeningPidsMap -Ports $ports

    if (Has-Listener -Map $map) {
        $bad = Get-BadOwners -Map $map -ExpectedNames @('python', 'pythonw')
        if ($bad.Count -eq 0) {
            Write-Host 'Flask already running on 5000 -> http://127.0.0.1:5000/ai/status'
            return
        }

        throw ('Port 5000 is occupied by non-python process: ' + ($bad -join ', '))
    }

    $python = Resolve-Python -FlaskDir $FlaskDir
    if (-not $python) {
        throw 'No usable yolov8 Python interpreter found for Flask service. Set YOLO_PYTHON to your yolov8 python.exe.'
    }

    Write-Host 'Starting Flask -> http://127.0.0.1:5000/ai/status'
    Write-Host ('Using python (yolov8): ' + $python)

    Push-Location $FlaskDir
    try {
        # Fast preflight: ensure yolov8 python itself can start.
        & $python -c "import sys; print(sys.executable)" *> $null
        if ($LASTEXITCODE -ne 0) {
            throw ('yolov8 python failed preflight, exit code: ' + $LASTEXITCODE + '. Check interpreter permissions and runtime dependencies.')
        }

        # Run in the current VS Code terminal, do not open a new window.
        & $python main.py
        if ($LASTEXITCODE -ne 0) {
            throw ('Flask process exited, exit code: ' + $LASTEXITCODE + '. If this is -1073741790, the yolov8 python runtime likely has permission/runtime issues.')
        }
    }
    finally {
        Pop-Location
    }
}

function Start-Spring {
    param([string]$SpringDir)

    $ports = @(9999)
    $map = Get-ListeningPidsMap -Ports $ports

    if (Has-Listener -Map $map) {
        $bad = Get-BadOwners -Map $map -ExpectedNames @('java')
        if ($bad.Count -eq 0) {
            Write-Host 'Spring already running on 9999 -> http://127.0.0.1:9999'
            return
        }

        throw ('Port 9999 is occupied by non-java process: ' + ($bad -join ', '))
    }

    $mvnw = Join-Path $SpringDir 'mvnw.cmd'
    if (-not (Test-Path $mvnw)) {
        throw ('mvnw.cmd not found in: ' + $SpringDir)
    }

    Write-Host 'Starting Spring -> http://127.0.0.1:9999'

    Push-Location $SpringDir
    try {
        & .\mvnw.cmd spring-boot:run -DskipTests
    }
    finally {
        Pop-Location
    }
}

function Start-Vite {
    param([string]$VueDir)

    $ports = @(8888, 8889)
    $map = Get-ListeningPidsMap -Ports $ports

    if (Has-Listener -Map $map) {
        $bad = Get-BadOwners -Map $map -ExpectedNames @('node', 'npm', 'pnpm', 'yarn')
        if ($bad.Count -eq 0) {
            Write-Host 'Vite already running on 8888/8889 -> http://localhost:8888/ (fallback http://localhost:8889/)'
            return
        }

        throw ('Port 8888/8889 is occupied by non-node process: ' + ($bad -join ', '))
    }

    $packageJson = Join-Path $VueDir 'package.json'
    if (-not (Test-Path $packageJson)) {
        throw ('package.json not found in: ' + $VueDir)
    }

    Write-Host 'Starting Vite -> http://localhost:8888/ (fallback http://localhost:8889/)'

    Push-Location $VueDir
    try {
        npm run dev
    }
    finally {
        Pop-Location
    }
}

function Get-HttpProbe {
    param(
        [string]$Url,
        [int]$TimeoutSec = 3
    )

    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        return @{
            hasResponse = $true
            statusCode = [int]$resp.StatusCode
            error = $null
        }
    }
    catch {
        $statusCode = $null
        try {
            if ($_.Exception.Response) {
                $statusCode = [int]$_.Exception.Response.StatusCode.value__
            }
        }
        catch {}

        if ($null -ne $statusCode) {
            return @{
                hasResponse = $true
                statusCode = $statusCode
                error = $null
            }
        }

        return @{
            hasResponse = $false
            statusCode = $null
            error = $_.Exception.Message
        }
    }
}

function Wait-HealthResult {
    param(
        [string]$Name,
        [ScriptBlock]$Probe,
        [int]$TimeoutSeconds,
        [int]$IntervalSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $last = $null

    while ((Get-Date) -lt $deadline) {
        try {
            $last = & $Probe
        }
        catch {
            $last = @{
                ok = $false
                message = $_.Exception.Message
            }
        }

        if ($last.ok) {
            Write-Host ('[OK] ' + $Name + ' -> ' + $last.message)
            return $true
        }

        Start-Sleep -Seconds $IntervalSeconds
    }

    if ($last -and $last.message) {
        Write-Host ('[WARN] ' + $Name + ' -> ' + $last.message)
    }
    else {
        Write-Host ('[WARN] ' + $Name + ' -> not ready within ' + $TimeoutSeconds + 's')
    }
    return $false
}

function Start-HealthWarn {
    $timeoutSeconds = 30
    $intervalSeconds = 1

    $parsedTimeout = 0
    if ([int]::TryParse($env:DEV_HEALTH_TIMEOUT_SECONDS, [ref]$parsedTimeout) -and $parsedTimeout -gt 0) {
        $timeoutSeconds = $parsedTimeout
    }

    $parsedInterval = 0
    if ([int]::TryParse($env:DEV_HEALTH_INTERVAL_SECONDS, [ref]$parsedInterval) -and $parsedInterval -gt 0) {
        $intervalSeconds = $parsedInterval
    }

    Write-Host ('Health check (warn-only): timeout=' + $timeoutSeconds + 's, interval=' + $intervalSeconds + 's')

    $flaskOk = Wait-HealthResult -Name 'Flask' -TimeoutSeconds $timeoutSeconds -IntervalSeconds $intervalSeconds -Probe {
        $url = 'http://127.0.0.1:5000/ai/status'
        $probe = Get-HttpProbe -Url $url -TimeoutSec 3
        if (-not $probe.hasResponse) {
            return @{
                ok = $false
                message = ($url + ' no response: ' + $probe.error)
            }
        }

        if ($probe.statusCode -eq 200) {
            return @{
                ok = $true
                message = ($url + ' (HTTP 200)')
            }
        }

        return @{
            ok = $false
            message = ($url + ' responded HTTP ' + $probe.statusCode + ', expected 200')
        }
    }

    $springOk = Wait-HealthResult -Name 'Spring' -TimeoutSeconds $timeoutSeconds -IntervalSeconds $intervalSeconds -Probe {
        $url = 'http://127.0.0.1:9999'
        $probe = Get-HttpProbe -Url $url -TimeoutSec 3
        if (-not $probe.hasResponse) {
            return @{
                ok = $false
                message = ($url + ' no response: ' + $probe.error)
            }
        }

        $code = [int]$probe.statusCode
        if (($code -ge 200 -and $code -lt 400) -or @(
                401,
                403,
                404
            ) -contains $code) {
            return @{
                ok = $true
                message = ($url + ' (HTTP ' + $code + ')')
            }
        }

        return @{
            ok = $false
            message = ($url + ' responded HTTP ' + $code + ', expected 2xx/3xx/401/403/404')
        }
    }

    $viteOk = Wait-HealthResult -Name 'Vite' -TimeoutSeconds $timeoutSeconds -IntervalSeconds $intervalSeconds -Probe {
        $urls = @(
            'http://127.0.0.1:8888/@vite/client',
            'http://127.0.0.1:8889/@vite/client'
        )

        foreach ($url in $urls) {
            $probe = Get-HttpProbe -Url $url -TimeoutSec 3
            if ($probe.hasResponse -and [int]$probe.statusCode -eq 200) {
                return @{
                    ok = $true
                    message = ($url + ' (HTTP 200)')
                }
            }
        }

        $details = @()
        foreach ($url in $urls) {
            $probe = Get-HttpProbe -Url $url -TimeoutSec 3
            if ($probe.hasResponse) {
                $details += ($url + ' HTTP ' + $probe.statusCode)
            }
            else {
                $details += ($url + ' no response')
            }
        }

        return @{
            ok = $false
            message = ('expected HTTP 200 from /@vite/client; ' + ($details -join '; '))
        }
    }

    $okCount = 0
    foreach ($result in @($flaskOk, $springOk, $viteOk)) {
        if ($result) {
            $okCount += 1
        }
    }

    if ($okCount -eq 3) {
        Write-Host '[OK] Health summary -> 3/3 services healthy'
    }
    else {
        Write-Host ('[WARN] Health summary -> ' + $okCount + '/3 healthy (warn-only, not blocking startup)')
    }
}

function Stop-DevServices {
    $ports = @(5000, 9999, 8888, 8889)
    $map = Get-ListeningPidsMap -Ports $ports
    $handled = @{}

    foreach ($port in $ports) {
        $pids = $map[$port]
        if ($pids.Count -eq 0) {
            Write-Host ('Port ' + $port + ' has no listener')
            continue
        }

        foreach ($procId in $pids) {
            if ($handled.ContainsKey($procId)) {
                continue
            }

            $handled[$procId] = $true
            $name = Get-ProcessNameById -ProcId $procId

            try {
                Stop-Process -Id $procId -Force -ErrorAction Stop
                Write-Host ('Stopped PID ' + $procId + ' (' + $name + ')')
            }
            catch {
                Write-Host ('Skip PID ' + $procId + ' (' + $name + '): ' + $_.Exception.Message)
            }
        }
    }
}

$projectRoot = Resolve-ProjectRoot
$flaskDir = Join-Path $projectRoot 'yolo_studentBehavior_detection_flask'
$springDir = Join-Path $projectRoot 'yolo_studentBehavior_detection_springboot'
$vueDir = Join-Path $projectRoot 'yolo_studentBehavior_detection_vue'

switch ($Service) {
    'Flask' { Start-Flask -FlaskDir $flaskDir }
    'Spring' { Start-Spring -SpringDir $springDir }
    'Vite' { Start-Vite -VueDir $vueDir }
    'Stop' { Stop-DevServices }
    'Health' { Start-HealthWarn }
}
