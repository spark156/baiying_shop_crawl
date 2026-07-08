$ErrorActionPreference = "Stop"

$chromeCandidates = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)

$chrome = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $chrome) {
    throw "Google Chrome was not found."
}

$profileRoot = Join-Path $env:LOCALAPPDATA "BaiyingDataTool"
$profile = Join-Path $profileRoot "chrome_profile_v2"
New-Item -ItemType Directory -Force -Path $profile | Out-Null

$url = "https://buyin.jinritemai.com/"
$argsList = @(
    "--remote-debugging-port=9222",
    "--user-data-dir=$profile",
    "--no-first-run",
    $url
)

Write-Host "Opening Google Chrome:"
Write-Host "  $chrome"
Write-Host "Profile:"
Write-Host "  $profile"
Write-Host ""
Write-Host "After logging in, keep this browser open and return to the web page."

Start-Process -FilePath $chrome -ArgumentList $argsList
