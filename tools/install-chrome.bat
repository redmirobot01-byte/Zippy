@echo off
setlocal enableextensions enabledelayedexpansion
chcp 65001 >nul
title Zippy - Chrome gözle / gurna

net session >nul 2>&1
if not "%errorlevel%"=="0" (
  echo.
  echo   [!] Bu faýly ADMINISTRATOR hokmunde isledin:
  echo       Fajla sag dwme - "Run as administrator"
  echo.
  pause
  exit /b 1
)

echo ==========================================
echo   1. Kompyuterde Chrome gozlenyar...
echo ==========================================
echo.

set "C1=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
set "C2=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
set "C3=%LocalAppData%\Google\Chrome\Application\chrome.exe"
set "FOUND="
for %%P in ("%C1%" "%C2%" "%C3%") do if exist "%%~P" set "FOUND=%%~P"

if defined FOUND (
  echo   TAPYLDY: !FOUND!
  echo   Acylyar...
  start "" "!FOUND!"
  goto :done
)

echo   Chrome.exe tapylmady - gurnamaga gechilyar.
echo.

echo ==========================================
echo   2. Gurnama (winget - Microsoft resmi)
echo ==========================================
where winget >nul 2>&1
if not errorlevel 1 (
  winget install --id Google.Chrome -e --accept-source-agreements --accept-package-agreements
  if not errorlevel 1 (
    echo   winget arkaly gurnaldy.
    goto :done
  )
  echo   winget bilen bolmady - göni faýl bilen synanyýarys.
)
echo.

echo ==========================================
echo   3. Goni faýl: dl.google.com (resmi)
echo ==========================================
set "DL=%TEMP%\ChromeSetup.exe"
if exist "%DL%" del /f /q "%DL%" >nul 2>&1
curl.exe -L --fail --retry 2 --connect-timeout 20 -o "%DL%" "https://dl.google.com/chrome/install/latest/chrome_installer.exe"
if exist "%DL%" (
  for %%A in ("%DL%") do if %%~zA GTR 1000000 (
    echo   Yuklendi. Gurnama acylyar...
    start "" "%DL%"
    goto :done
  )
)

echo   Exe yuklenmedi. MSI bilen synanyýarys...
set "MSI=%TEMP%\ChromeEnterprise64.msi"
if exist "%MSI%" del /f /q "%MSI%" >nul 2>&1
curl.exe -L --fail --retry 2 --connect-timeout 20 -o "%MSI%" "https://dl.google.com/dl/chrome/install/googlechromestandaloneenterprise64.msi"
if exist "%MSI%" (
  for %%A in ("%MSI%") do if %%~zA GTR 1000000 (
    echo   MSI yuklendi. Ümsüm gurnama...
    msiexec /i "%MSI%" /passive /norestart
    echo   Gurnaldy.
    goto :done
  )
)

echo.
echo   [!] Hiç zat yuklenmedi.
echo       Sebap: internet/proxy. Ilki fix-windows-browser.bat isledin,
echo       ýa-da faýly telefonyňyzdan yuklap, USB bilen gechirin.
echo.

:done
echo.
echo   Tayyar. Chrome-y Baslatmenýudan ("Chrome" ýa-da "Hrom") gozlan.
echo   Profil (zakladkalar, parollar) saklanan bolsa - Chrome-a girip
echo   öz hasabynyz bilen sine-in edin: hemmesi yzyna geler.
echo.
pause
endlocal
