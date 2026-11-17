<#
  Zippy - Chrome gözleg (find-chrome.ps1)
  Administrator gerek däl. Diňe okaýar, hiç zat pozmaýar.
#>
$ErrorActionPreference = 'SilentlyContinue'
$host.UI.RawUI.WindowTitle = 'Zippy - Chrome gözleg'
function Line($t, $c) { Write-Host $t -ForegroundColor $c }

Line '==================================================' Cyan
Line '   CHROME GÖZLEÝÄRIS (diňe okaýar, hiç zat pozmaýar)' Cyan
Line '==================================================' Cyan

$found = New-Object System.Collections.Generic.List[string]

Line "`n[1] Standart ýerler:" Yellow
$paths = @(
  "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  "$env:LocalAppData\Google\Chrome\Application\chrome.exe",
  "$env:ProgramData\Google\Chrome\Application\chrome.exe",
  "$env:SystemDrive\Google\Chrome\Application\chrome.exe"
)
foreach ($p in $paths) {
  if ($p -and (Test-Path -LiteralPath $p)) { Line "   [BAR]  $p" Green; $found.Add($p) }
  else { Line "   [ýok]  $p" DarkGray }
}

Line "`n[2] Registr (Goşulan programmalar sanawy):" Yellow
$keys = @(
  'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
$apps = foreach ($k in $keys) { Get-ItemProperty $k }
$chromeApps = $apps | Where-Object { $_.DisplayName -match 'Chrome|Хром|Chromium' }
if ($chromeApps) {
  foreach ($a in $chromeApps) {
    Line ("   [BAR]  " + $a.DisplayName + "  wersiýa: " + $a.DisplayVersion) Green
    if ($a.InstallLocation) { Line ("          Ýeri: " + $a.InstallLocation) Gray }
  }
} else { Line '   [ýok]  Sanawda Chrome ýazgysy tapylmady' DarkGray }

Line "`n[3] App Paths (Windows öz ýerini bilýärmi?):" Yellow
$appPathKeys = @(
  'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe',
  'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe'
)
$anyAppPath = $false
foreach ($k in $appPathKeys) {
  $item = Get-Item -LiteralPath $k
  if ($item) {
    $v = $item.GetValue('')
    if ($v) { Line "   [BAR]  $v" Green; $found.Add(($v -replace '^"|"$','')); $anyAppPath = $true }
  }
}
if (-not $anyAppPath) { Line '   [ýok]  App Paths ýazgysy ýok' DarkGray }

Line "`n[4] Baslatmenýu ýazgylary (shortcut-lar):" Yellow
$smDirs = @(
  "$env:ProgramData\Microsoft\Windows\Start Menu\Programs",
  "$env:AppData\Microsoft\Windows\Start Menu\Programs",
  "$env:UserProfile\Desktop",
  "$env:PUBLIC\Desktop"
)
$sh = foreach ($d in $smDirs) { Get-ChildItem -LiteralPath $d -Recurse -Force | Where-Object { $_.Name -match 'Chrome|Хром' } }
if ($sh) { foreach ($s in $sh) { Line ("   [BAR]  " + $s.FullName) Green } }
else { Line '   [ýok]  Shortcut tapylmady' DarkGray }

if ($found.Count -eq 0) {
  Line "`n[5] Giňişleýin gözleg (C: diski, 1-3 minut)..." Yellow
  $deep = Get-ChildItem -LiteralPath "$env:SystemDrive\" -Filter 'chrome.exe' -Recurse -Force -Depth 6 |
          Where-Object { $_.FullName -match 'Chrome' } | Select-Object -First 5
  if ($deep) { foreach ($d in $deep) { Line ("   [BAR]  " + $d.FullName) Green; $found.Add($d.FullName) } }
  else { Line '   [ýok]  C: diskinde chrome.exe tapylmady' DarkGray }
}

Line "`n==================================================" Cyan
if ($found.Count -gt 0) {
  Line ("  NETIJE: Chrome BAR (" + $found.Count + " ýerde). Ony pozmaň!") Green
  Line ("  Açmak üçin: " + $found[0]) Green
  $ans = Read-Host "`n  Häzir açmalymy? (h = hawa, Enter = ýok)"
  if ($ans -match '^(h|y|ý)$') { Start-Process $found[0] }
} else {
  Line '  NETIJE: Chrome kompýuterde GURNALMADYK.' Yellow
  Line '  Gurnamak üçin tools\install-chrome.bat (Administrator) işlediň.' Yellow
  Line '  Ýa-da: https://www.google.com/chrome/' Yellow
}
Line "`n  Islendik düwmä basyp ýapyň..." Cyan
try { [void]$Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown') } catch { Read-Host 'Enter' | Out-Null }
