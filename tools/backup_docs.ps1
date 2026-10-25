# Backup documents/ and the root tracker to a dated zip.
#
# Why: documents/ and job_search_tracker.csv are the ONLY local copies of
# candidate job-search material; both are gitignored and need one backup.
#
# Usage (from anywhere):
#   powershell -ExecutionPolicy Bypass -File tools\backup_docs.ps1
#   powershell -ExecutionPolicy Bypass -File tools\backup_docs.ps1 -Dest D:\MyBackup
#
# Keeps the newest 10 archives, deletes older ones.

param(
    [string]$Repo = "",
    [string]$Dest = "$Env:USERPROFILE\Backup\jobseeker-assistant",
    [int]$Keep = 10
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Repo)) {
    $Repo = Split-Path -Parent $PSScriptRoot
}

$src = Join-Path $Repo "documents"
$tracker = Join-Path $Repo "job_search_tracker.csv"
if (-not (Test-Path $src)) {
    throw "documents folder not found under repo: $Repo"
}
if (-not (Test-Path $tracker)) {
    throw "job_search_tracker.csv not found under repo: $Repo"
}

if (-not (Test-Path $Dest)) {
    New-Item -ItemType Directory -Path $Dest -Force | Out-Null
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stage = Join-Path $env:TEMP ("jobseeker-assistant-backup-" + $stamp)
New-Item -ItemType Directory -Path $stage -Force | Out-Null
try {
    Copy-Item $src (Join-Path $stage "documents") -Recurse -Force
    Copy-Item $tracker (Join-Path $stage "job_search_tracker.csv") -Force
    $zip = Join-Path $Dest ("documents-" + $stamp + ".zip")
    Compress-Archive -Path (Join-Path $stage "documents"), (Join-Path $stage "job_search_tracker.csv") -DestinationPath $zip -CompressionLevel Optimal
    $info = Get-Item $zip
    $mb = [math]::Round($info.Length / 1MB, 2)
    $count = (Get-ChildItem $src -Recurse -File | Measure-Object).Count + 1
    Write-Output ("BACKUP_OK " + $zip + " | " + $mb + " MB | " + $count + " files including tracker")

    $old = Get-ChildItem $Dest -Filter "documents-*.zip" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip $Keep
    if ($old) {
        $old | Remove-Item -Force
        Write-Output ("PRUNED " + $old.Count + " old archive(s), keeping newest " + $Keep)
    }
} finally {
    Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
}
