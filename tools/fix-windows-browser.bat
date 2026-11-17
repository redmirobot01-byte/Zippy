@echo off
setlocal enableextensions
chcp 65001 >nul
title Zippy VPN - Windows tor bejergisi

net session >nul 2>&1
if not "%errorlevel%"=="0" (
  echo.
  echo   [!] Bu faýly ADMINISTRATOR hökmünde işlediň!
  echo       Faýla sag düwme basyp - "Run as administrator" saýlaň.
  echo.
  pause
  exit /b 1
)

echo ============================================
echo   Zippy VPN - Windows brauzer bejergisi
echo ============================================
echo.

echo [1/7] Ulgam proksisi aýrylýar...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f >nul
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyServer /f >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyOverride /f >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v AutoConfigURL /f >nul 2>&1
reg delete "HKLM\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v AutoConfigURL /f >nul 2>&1
netsh winhttp reset proxy >nul

echo [2/7] DNS keşi arassalanýar...
ipconfig /flushdns >nul
ipconfig /registerdns >nul 2>&1
ipconfig /release >nul 2>&1
ipconfig /renew >nul 2>&1

echo [3/7] DNS awtomatik (DHCP) derejesine goýulýar...
netsh interface ip set dns name="Wi-Fi" source=dhcp >nul 2>&1
netsh interface ip set dns name="Ethernet" source=dhcp >nul 2>&1
netsh interface ipv4 set dnsservers name="Wi-Fi" source=dhcp >nul 2>&1
netsh interface ipv4 set dnsservers name="Ethernet" source=dhcp >nul 2>&1

echo [4/7] Galan VPN adapterleri (Happ / Wintun / TAP / WireGuard) öçürilýär...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.InterfaceDescription -match 'Happ|wintun|WinTun|TAP-|TAP Windows|WireGuard|Clash|sing-box' } | ForEach-Object { Disable-NetAdapter -Name $_.Name -Confirm:$false -ErrorAction SilentlyContinue }" >nul 2>&1

echo [5/7] Winsock we TCP/IP täzelenýär...
netsh winsock reset >nul
netsh int ip reset >nul 2>&1

echo [6/7] Windows tora özüni täzeden gözleýär...
netsh int ip set global taskoffload=enabled >nul 2>&1
netsh advfirewall firewall delete rule name="ZippyBlok" >nul 2>&1

echo [7/7] Explorer täzelenýär...
taskkill /f /im explorer.exe >nul 2>&1
start "" explorer.exe >nul 2>&1

echo.
echo   TAÝÝAR! Indi KOMPÝUTERI TÄZEDEN AÇYŇ (Restart),
echo   soňra brauzeri açyp barlaň.
echo.
echo   Eger barybir işlemese: sagat-senäni barlaň we
echo   C:\Windows\System32\drivers\etc\hosts faýlyny açyp görüň.
echo.
pause
endlocal
