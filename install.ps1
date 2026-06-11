<#
.SYNOPSIS
    Quenza Cloud Toolkit - Installer (Windows / PowerShell)

.DESCRIPTION
    Otomatis: download -> cek prasyarat -> venv -> dependencies -> .env
    (Master Password acak terenkripsi) -> daftarkan service (NSSM, fallback
    Task Scheduler) -> jalankan & verifikasi. Bila ada tahap gagal, menawarkan
    lapor isu ke GitHub.

.EXAMPLE
    PS> .\install.ps1
    PS> irm https://raw.githubusercontent.com/teguh02/quenza-cloud-toolkit/main/install.ps1 | iex
#>

[CmdletBinding()]
param(
    [string]$InstallDir = "",
    [int]$Port = 0,
    [string]$PublicUrl = ""
)

$ErrorActionPreference = "Stop"

# --- Constants ---------------------------------------------------------------
$RepoUrl    = "https://github.com/teguh02/quenza-cloud-toolkit.git"
$RepoZip    = "https://github.com/teguh02/quenza-cloud-toolkit/archive/refs/heads/main.zip"
$IssuesUrl  = "https://github.com/teguh02/quenza-cloud-toolkit/issues/new"
$NssmUrl    = "https://nssm.cc/release/nssm-2.24.zip"
$AppModule  = "app.main:app"
$ServiceName = "Quenza"
$MinPyMinor = 10
$DefaultPort = 8000

# --- State -------------------------------------------------------------------
$script:CurrentStep = "inisialisasi"
$script:PyBin       = ""
$script:HasGit      = $false
$script:IsAdmin     = $false
$script:Arch        = ""
$script:HostIp      = "127.0.0.1"
$script:MasterPassword = ""
$script:LogFile     = ""
$script:ServiceKind = ""   # nssm | task

# --- Logging -----------------------------------------------------------------
function Write-Log {
    param([string]$Message, [string]$Color = "Gray")
    Write-Host $Message -ForegroundColor $Color
    if ($script:LogFile) {
        try { Add-Content -LiteralPath $script:LogFile -Value ($Message -replace '\x1b\[[0-9;]*m','') -ErrorAction SilentlyContinue } catch {}
    }
}
function Log-Info { param([string]$m) Write-Log "  - $m" "Cyan" }
function Log-Ok   { param([string]$m) Write-Log "  [OK] $m" "Green" }
function Log-Warn { param([string]$m) Write-Log "  [!] $m" "Yellow" }
function Log-Err  { param([string]$m) Write-Log "  [X] $m" "Red" }
function Log-Step { param([string]$m) Write-Log "`n==> $m" "White" }

function Show-Banner {
    Write-Log ""
    Write-Log "  ___                            " "Cyan"
    Write-Log " / _ \ _   _  ___ _ __  ____ _   " "Cyan"
    Write-Log "| | | | | | |/ _ \ '_ \|_  / _\` |   Quenza Cloud Toolkit" "Cyan"
    Write-Log "| |_| | |_| |  __/ | | |/ / (_| |   Installer (Windows)" "Cyan"
    Write-Log " \__\_\\__,_|\___|_| |_/___\__,_|" "Cyan"
    Write-Log ""
}

# --- Failure handling + issue reporting --------------------------------------
function Open-IssueReport {
    param([string]$Step, [string]$Detail)
    Write-Log ""
    Log-Warn "Instalasi gagal pada tahap: $Step"
    if ($Detail) { Write-Log $Detail "DarkGray" }
    Write-Log ""
    $answer = Read-Host "Laporkan masalah ini sebagai isu di GitHub? [y/N]"
    if ($answer -match '^(y|yes)$') {
        $pyVer = if ($script:PyBin) { (& $script:PyBin --version 2>&1) } else { "tidak ada" }
        $title = "[Install] Gagal pada tahap: $Step"
        $body  = @"
**Tahap gagal:** $Step

**Detail error:**
``````
$Detail
``````

**Lingkungan:**
- OS: Windows ($($script:Arch))
- Python: $pyVer
- Administrator: $($script:IsAdmin)
- Direktori instalasi: $InstallDir

**Langkah reproduksi:**
1. Jalankan install.ps1
2. ...
"@
        Add-Type -AssemblyName System.Web
        $url = "$IssuesUrl`?title=$([System.Web.HttpUtility]::UrlEncode($title))&body=$([System.Web.HttpUtility]::UrlEncode($body))"
        try {
            Start-Process $url | Out-Null
            Log-Ok "Browser dibuka untuk membuat isu."
        } catch {
            Log-Info "Buka URL berikut di browser untuk melaporkan:"
            Write-Log $url "Cyan"
        }
    }
}

function Invoke-Fail {
    param([string]$Detail = "")
    Log-Err "Terjadi kesalahan."
    Open-IssueReport -Step $script:CurrentStep -Detail $Detail
    Write-Log ""
    Log-Info "Log lengkap: $($script:LogFile)"
    exit 1
}

function Invoke-Step {
    param([string]$Label, [scriptblock]$Action)
    $script:CurrentStep = $Label
    Log-Step $Label
    try {
        & $Action
    } catch {
        Invoke-Fail -Detail $_.Exception.Message
    }
}

# --- Detection ---------------------------------------------------------------
function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p  = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-HostIp {
    try {
        $ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
            Select-Object -First 1).IPAddress
        if ($ip) { return $ip }
    } catch {}
    return "127.0.0.1"
}

function Test-PythonVersion {
    param([string]$Bin)
    try {
        & $Bin -c "import sys; raise SystemExit(0 if sys.version_info >= (3, $MinPyMinor) else 1)" 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

function Find-Python {
    foreach ($cand in @("python", "python3", "py")) {
        $cmd = Get-Command $cand -ErrorAction SilentlyContinue
        if ($cmd) {
            $exe = $cmd.Source
            if (-not $exe -and $cand -eq "py") { $exe = "py" }
            if (Test-PythonVersion $exe) { return $exe }
        }
    }
    return $null
}

function Initialize-Detection {
    $script:CurrentStep = "deteksi sistem"
    $script:Arch = $env:PROCESSOR_ARCHITECTURE
    $script:IsAdmin = Test-Admin
    $script:HasGit = [bool](Get-Command git -ErrorAction SilentlyContinue)
    $script:HostIp = Get-HostIp

    Log-Ok "OS: Windows ($($script:Arch))"
    Log-Ok "Administrator: $($script:IsAdmin)"
    Log-Ok "git: $(if ($script:HasGit) { 'tersedia' } else { 'tidak (akan pakai download arsip)' })"
}

function Initialize-Python {
    $script:CurrentStep = "memeriksa Python"
    $found = Find-Python
    if ($found) {
        $script:PyBin = $found
        Log-Ok "Python ditemukan: $(& $found --version 2>&1) ($found)"
        return
    }
    Log-Err "Python $MinPyMinor+ tidak ditemukan."
    Log-Info "Pasang Python dari https://www.python.org/downloads/windows/"
    Log-Info "Saat instalasi, centang 'Add python.exe to PATH'. Lalu jalankan ulang script ini."
    Log-Info "Atau via winget:  winget install -e --id Python.Python.3.12"
    Invoke-Fail -Detail "Python $MinPyMinor+ tidak tersedia di PATH."
}

function Test-DbTools {
    $script:CurrentStep = "memeriksa tools database (opsional)"
    $missing = @()
    if (Get-Command mysqldump -ErrorAction SilentlyContinue) { Log-Ok "mysqldump tersedia" } else { $missing += "mysqldump" }
    if (Get-Command pg_dump -ErrorAction SilentlyContinue) { Log-Ok "pg_dump tersedia" } else { $missing += "pg_dump" }
    if ($missing.Count -gt 0) {
        Log-Warn "Tools backup database belum lengkap: $($missing -join ', ')"
        Log-Info "Ini opsional - backup direktori/file tetap berjalan. Pasang MySQL/PostgreSQL client bila perlu, atau set MYSQLDUMP_PATH/PG_DUMP_PATH di .env."
    }
}

# --- Prompts -----------------------------------------------------------------
function Read-Inputs {
    $script:CurrentStep = "konfigurasi instalasi"

    if (-not $InstallDir) {
        $default = Join-Path $env:LOCALAPPDATA "QuenzaCloudToolkit"
        $inp = Read-Host "Lokasi instalasi [$default]"
        $script:InstallDirResolved = if ([string]::IsNullOrWhiteSpace($inp)) { $default } else { $inp }
    } else {
        $script:InstallDirResolved = $InstallDir
    }
    $global:InstallDir = $script:InstallDirResolved

    if ($Port -le 0) {
        $inp = Read-Host "Port aplikasi [$DefaultPort]"
        $Port = if ([string]::IsNullOrWhiteSpace($inp)) { $DefaultPort } else { [int]$inp }
    }
    if (Test-PortInUse $Port) {
        Log-Warn "Port $Port sedang dipakai."
        $inp = Read-Host "Masukkan port lain [8080]"
        $Port = if ([string]::IsNullOrWhiteSpace($inp)) { 8080 } else { [int]$inp }
    }
    $global:Port = $Port

    if (-not $PublicUrl) {
        Log-Info "Public URL opsional untuk reverse proxy (mis. https://quenza.domain.com)."
        Log-Info "Kosongkan bila akses langsung via IP/port. Penting untuk OAuth Google Drive."
        $inp = Read-Host "Public URL [kosong]"
        $PublicUrl = $inp
    }
    $global:PublicUrl = $PublicUrl.TrimEnd('/')

    Log-Ok "Lokasi: $($global:InstallDir) | Port: $($global:Port) | Public URL: $(if ($global:PublicUrl) { $global:PublicUrl } else { '(tidak ada)' })"
}

function Test-PortInUse {
    param([int]$P)
    try {
        $conns = Get-NetTCPConnection -State Listen -LocalPort $P -ErrorAction SilentlyContinue
        return [bool]$conns
    } catch { return $false }
}

# --- Stage: download ---------------------------------------------------------
function Get-Project {
    if ((Test-Path (Join-Path $global:InstallDir ".git")) -and $script:HasGit) {
        Log-Info "Repo sudah ada - memperbarui (git pull)..."
        git -C $global:InstallDir pull --ff-only
        if ($LASTEXITCODE -ne 0) { throw "git pull gagal." }
        return
    }
    if (Test-Path (Join-Path $global:InstallDir "app\main.py")) {
        Log-Info "Direktori instalasi sudah berisi project - melewati download."
        return
    }

    New-Item -ItemType Directory -Path $global:InstallDir -Force | Out-Null

    if ($script:HasGit) {
        Log-Info "Meng-clone repository..."
        git clone --depth 1 $RepoUrl $global:InstallDir
        if ($LASTEXITCODE -ne 0) { throw "git clone gagal." }
    } else {
        Log-Info "git tidak ada - mengunduh arsip..."
        $tmp = Join-Path $env:TEMP ("quenza_" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $tmp -Force | Out-Null
        $zip = Join-Path $tmp "quenza.zip"
        Invoke-WebRequest -Uri $RepoZip -OutFile $zip -UseBasicParsing
        Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force
        $extracted = Get-ChildItem -LiteralPath $tmp -Directory | Where-Object { $_.Name -like "quenza-cloud-toolkit-*" } | Select-Object -First 1
        if (-not $extracted) { throw "Struktur arsip tidak dikenali." }
        Copy-Item -Path (Join-Path $extracted.FullName "*") -Destination $global:InstallDir -Recurse -Force
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# --- Stage: venv + deps ------------------------------------------------------
function Initialize-Venv {
    Set-Location $global:InstallDir
    $venvPy = Join-Path $global:InstallDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPy)) {
        & $script:PyBin -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "Gagal membuat virtual environment." }
    }
    & $venvPy -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Gagal upgrade pip." }
    & $venvPy -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Gagal memasang dependencies." }
}

# --- Stage: .env -------------------------------------------------------------
function Set-EnvVar {
    param([string]$Key, [string]$Value)
    $venvPy = Join-Path $global:InstallDir ".venv\Scripts\python.exe"
    $envFile = Join-Path $global:InstallDir ".env"
    $py = @"
import sys, io
path, key, value = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    with io.open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
except FileNotFoundError:
    lines = []
out, found = [], False
for ln in lines:
    if ln.lstrip().startswith(key + '='):
        out.append(key + '=' + value + '\n'); found = True
    else:
        out.append(ln)
if not found:
    if out and not out[-1].endswith('\n'):
        out[-1] += '\n'
    out.append(key + '=' + value + '\n')
with io.open(path, 'w', encoding='utf-8') as f:
    f.writelines(out)
"@
    $tmpPy = Join-Path $env:TEMP ("setenv_" + [guid]::NewGuid().ToString("N") + ".py")
    Set-Content -LiteralPath $tmpPy -Value $py -Encoding UTF8
    & $venvPy $tmpPy $envFile $Key $Value
    Remove-Item -LiteralPath $tmpPy -ErrorAction SilentlyContinue
    if ($LASTEXITCODE -ne 0) { throw "Gagal menulis $Key ke .env." }
}

function Initialize-EnvConfig {
    Set-Location $global:InstallDir
    $envFile = Join-Path $global:InstallDir ".env"
    if (-not (Test-Path $envFile)) {
        Copy-Item ".env.example" ".env"
        Log-Ok "Membuat .env dari .env.example"
    } else {
        Log-Info ".env sudah ada - memperbarui kunci yang diperlukan saja."
    }

    $venvPy = Join-Path $global:InstallDir ".venv\Scripts\python.exe"

    $secret = (& $venvPy -c "import secrets; print(secrets.token_urlsafe(48))").Trim()
    Set-EnvVar "SECRET_KEY" $secret

    $enc = (& $venvPy -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())").Trim()
    Set-EnvVar "ENCRYPTION_KEY" $enc

    $script:MasterPassword = (& $venvPy -c "import secrets; print(secrets.token_urlsafe(18))").Trim()
    $hashLine = (& $venvPy generate_hash.py $script:MasterPassword | Select-String '^MASTER_PASSWORD_HASH=').Line
    if (-not $hashLine) { throw "Gagal membuat hash Master Password." }
    $hash = $hashLine -replace '^MASTER_PASSWORD_HASH=', ''
    Set-EnvVar "MASTER_PASSWORD_HASH" $hash

    Set-EnvVar "DEBUG" "true"

    if ($global:PublicUrl) {
        $redirect = "$($global:PublicUrl)/destinations/gdrive/callback"
    } else {
        $redirect = "http://$($script:HostIp):$($global:Port)/destinations/gdrive/callback"
    }
    Set-EnvVar "GOOGLE_REDIRECT_URI" $redirect

    Log-Ok "Konfigurasi .env selesai (SECRET_KEY, ENCRYPTION_KEY, Master Password, redirect URI)."
}

# --- Stage: verify -----------------------------------------------------------
function Test-AppImport {
    Set-Location $global:InstallDir
    $venvPy = Join-Path $global:InstallDir ".venv\Scripts\python.exe"
    & $venvPy -c "from app.main import app; print('app import OK')"
    if ($LASTEXITCODE -ne 0) { throw "Gagal mengimpor aplikasi." }
}

# --- Stage: service ----------------------------------------------------------
function Get-Nssm {
    # Returns path to nssm.exe (downloads if needed), or $null on failure.
    $nssmDir = Join-Path $global:InstallDir "nssm"
    $archDir = if ($script:Arch -match '64') { "win64" } else { "win32" }
    $nssmExe = Join-Path $nssmDir "nssm.exe"
    if (Test-Path $nssmExe) { return $nssmExe }

    try {
        New-Item -ItemType Directory -Path $nssmDir -Force | Out-Null
        $tmp = Join-Path $env:TEMP ("nssm_" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $tmp -Force | Out-Null
        $zip = Join-Path $tmp "nssm.zip"
        Invoke-WebRequest -Uri $NssmUrl -OutFile $zip -UseBasicParsing
        Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force
        $src = Get-ChildItem -LiteralPath $tmp -Recurse -Filter "nssm.exe" |
            Where-Object { $_.FullName -match "\\$archDir\\" } | Select-Object -First 1
        if (-not $src) { return $null }
        Copy-Item -LiteralPath $src.FullName -Destination $nssmExe -Force
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
        return $nssmExe
    } catch {
        return $null
    }
}

function Install-NssmService {
    $nssm = Get-Nssm
    if (-not $nssm) { return $false }

    $venvPy = Join-Path $global:InstallDir ".venv\Scripts\python.exe"
    $args = "-m uvicorn $AppModule --host 0.0.0.0 --port $($global:Port) --proxy-headers --forwarded-allow-ips=*"

    # Remove existing service if present (ignore errors)
    & $nssm stop $ServiceName 2>$null | Out-Null
    & $nssm remove $ServiceName confirm 2>$null | Out-Null

    & $nssm install $ServiceName $venvPy $args
    if ($LASTEXITCODE -ne 0) { return $false }
    & $nssm set $ServiceName AppDirectory $global:InstallDir | Out-Null
    & $nssm set $ServiceName Start SERVICE_AUTO_START | Out-Null
    & $nssm set $ServiceName AppStdout (Join-Path $global:InstallDir "server.log") | Out-Null
    & $nssm set $ServiceName AppStderr (Join-Path $global:InstallDir "server.log") | Out-Null
    & $nssm set $ServiceName AppExit Default Restart | Out-Null
    & $nssm start $ServiceName | Out-Null
    $script:ServiceKind = "nssm"
    return $true
}

function Install-ScheduledTask {
    # Fallback: Task Scheduler at startup.
    $venvPy = Join-Path $global:InstallDir ".venv\Scripts\python.exe"
    $argList = "-m uvicorn $AppModule --host 0.0.0.0 --port $($global:Port) --proxy-headers --forwarded-allow-ips=*"
    try {
        $action = New-ScheduledTaskAction -Execute $venvPy -Argument $argList -WorkingDirectory $global:InstallDir
        $trigger = New-ScheduledTaskTrigger -AtStartup
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
        $principal = if ($script:IsAdmin) {
            New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
        } else {
            New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive
        }
        Unregister-ScheduledTask -TaskName $ServiceName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
        Register-ScheduledTask -TaskName $ServiceName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
        Start-ScheduledTask -TaskName $ServiceName -ErrorAction SilentlyContinue | Out-Null
        $script:ServiceKind = "task"
        return $true
    } catch {
        return $false
    }
}

function Register-QuenzaService {
    if ($script:IsAdmin) {
        Log-Info "Mendaftarkan Windows Service via NSSM..."
        if (Install-NssmService) {
            Log-Ok "Windows Service '$ServiceName' terpasang & berjalan."
            return
        }
        Log-Warn "NSSM gagal - beralih ke Task Scheduler."
    } else {
        Log-Warn "Tidak berjalan sebagai Administrator - memakai Task Scheduler (bukan Service)."
    }
    if (Install-ScheduledTask) {
        Log-Ok "Scheduled Task '$ServiceName' terpasang (auto-start)."
    } else {
        throw "Gagal mendaftarkan layanan (NSSM & Task Scheduler keduanya gagal). Jalankan PowerShell sebagai Administrator dan coba lagi."
    }
}

# --- Stage: health check -----------------------------------------------------
function Test-Health {
    $url = "http://127.0.0.1:$($global:Port)/healthz"
    for ($i = 0; $i -lt 20; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            if ($resp.StatusCode -eq 200) { return $true }
        } catch {}
        Start-Sleep -Seconds 1
    }
    return $false
}

# --- Summary -----------------------------------------------------------------
function Show-Summary {
    $access = if ($global:PublicUrl) { $global:PublicUrl } else { "http://$($script:HostIp):$($global:Port)" }
    Write-Log ""
    Write-Log "========================================================" "Green"
    Write-Log "  Quenza Cloud Toolkit berhasil dipasang & berjalan!    " "Green"
    Write-Log "========================================================" "Green"
    Write-Log ""
    Write-Log "  URL Akses     : $access" "White"
    Write-Log "  Lokal         : http://127.0.0.1:$($global:Port)" "White"
    Write-Log "  Lokasi        : $($global:InstallDir)" "White"
    Write-Log "  Service       : $ServiceName ($($script:ServiceKind))" "White"
    Write-Log ""
    Write-Log "  Master Password (SIMPAN - hanya tampil sekali):" "Yellow"
    Write-Log "  $($script:MasterPassword)" "White"
    Write-Log ""
    if ($script:ServiceKind -eq "nssm") {
        Write-Log "  Kelola service:" "DarkGray"
        Write-Log "    sc query $ServiceName" "DarkGray"
        Write-Log "    .\nssm\nssm.exe restart $ServiceName  (dari folder instalasi)" "DarkGray"
        Write-Log "    Log: $($global:InstallDir)\server.log" "DarkGray"
    } else {
        Write-Log "  Kelola task: Task Scheduler -> '$ServiceName'" "DarkGray"
        Write-Log "  Log: $($global:InstallDir)\server.log" "DarkGray"
    }
    if ($global:PublicUrl) {
        Write-Log ""
        Write-Log "  Reverse proxy: arahkan $($global:PublicUrl) -> 127.0.0.1:$($global:Port)" "Yellow"
        Write-Log "  Google Drive: daftarkan redirect URI di Google Cloud Console:" "Yellow"
        Write-Log "    $($global:PublicUrl)/destinations/gdrive/callback" "Yellow"
    }
    Write-Log ""
}

# --- Main --------------------------------------------------------------------
function Main {
    Show-Banner
    Initialize-Detection

    $script:LogFile = Join-Path $env:TEMP "quenza_install.log"

    Read-Inputs

    # Move log into install dir
    try {
        New-Item -ItemType Directory -Path $global:InstallDir -Force | Out-Null
        $newLog = Join-Path $global:InstallDir "install.log"
        if (Test-Path $script:LogFile) { Get-Content $script:LogFile | Add-Content $newLog -ErrorAction SilentlyContinue }
        $script:LogFile = $newLog
    } catch {}

    Initialize-Python
    Test-DbTools

    Invoke-Step "Mengunduh project" { Get-Project }
    Invoke-Step "Menyiapkan virtual environment & dependencies" { Initialize-Venv }
    Invoke-Step "Mengonfigurasi .env (Master Password terenkripsi)" { Initialize-EnvConfig }
    Invoke-Step "Memverifikasi aplikasi" { Test-AppImport }
    Invoke-Step "Mendaftarkan service (auto-startup)" { Register-QuenzaService }

    $script:CurrentStep = "memverifikasi layanan berjalan"
    Log-Step "Memverifikasi layanan berjalan"
    if (Test-Health) {
        Log-Ok "Layanan merespons di /healthz."
    } else {
        Log-Warn "Layanan belum merespons health check. Periksa log: $($global:InstallDir)\server.log"
    }

    Show-Summary
}

Main
