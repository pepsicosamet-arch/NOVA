@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title NOVA derleniyor

echo.
echo  ==========================================
echo    NOVA - EXE ve kurulum dosyasi (Samet Sahin)
echo  ==========================================
echo.

rem ---- 1) Uygun Python'u bul: 3.12 ya da 3.13 (yoksa 3.12'yi otomatik kur) ----
set "PY312=%LocalAppData%\Programs\Python\Python312\python.exe"
set "PY="
if exist "%PY312%" set "PY="%PY312%""
if not defined PY py -3.12 -c "print()" >nul 2>&1 && set "PY=py -3.12"
if not defined PY py -3.13 -c "print()" >nul 2>&1 && set "PY=py -3.13"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info[:2] in ((3,12),(3,13)) else 1)" >nul 2>&1 && set "PY=python"
if not defined PY call :installpython
if not defined PY goto :nopython
echo [1/5] Python bulundu: %PY%

rem ---- 2) Sanal ortam ----
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info[:2] in ((3,12),(3,13)) else 1)" >nul 2>&1 || rmdir /s /q .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo [2/5] Sanal ortam olusturuluyor...
  %PY% -m venv .venv
  if errorlevel 1 goto :fail
) else (
  echo [2/5] Sanal ortam hazir.
)
set "VPY=%~dp0.venv\Scripts\python.exe"
if not exist "%VPY%" goto :fail

rem ---- 3) Paketler ----
echo [3/5] Paketler yukleniyor (ilk seferde birkac dakika surer)...
"%VPY%" -m pip install --upgrade pip
"%VPY%" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :fail

rem ---- 4) EXE ----
echo [4/5] NOVA.exe olusturuluyor...
if exist build rmdir /s /q build
if exist dist\NOVA rmdir /s /q dist\NOVA
"%VPY%" -m PyInstaller --noconfirm --clean --windowed --name NOVA ^
  --icon "assets\nova.ico" ^
  --add-data "web;web" ^
  --add-data "assets;assets" ^
  --collect-all _sounddevice_data ^
  --collect-all _soundfile_data ^
  main.py
if errorlevel 1 goto :fail
if not exist "dist\NOVA\NOVA.exe" goto :fail
echo        Tamam: dist\NOVA\NOVA.exe

rem ---- 5) Kurulum dosyasi ----
echo [5/5] Kurulum dosyasi olusturuluyor...
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC goto :noinno
"%ISCC%" "installer\nova.iss"
if errorlevel 1 goto :fail
echo.
echo  BITTI. Kurulum dosyasi: Output\NOVA-1.3.0-Windows-Setup.exe
goto :end

:noinno
echo.
echo  Inno Setup 6 bulunamadi, sadece EXE olusturuldu: dist\NOVA\NOVA.exe
echo  Kurulum dosyasi icin Inno Setup 6 kur: https://jrsoftware.org/isdl.php
echo  sonra build.bat'i tekrar calistir.
goto :end

rem ================= Python 3.12 otomatik kurulum =================
:installpython
echo [1/5] Python 3.12 bulunamadi. Otomatik indirilip kuruluyor (yaklasik 25 MB)...
echo        Bilgisayarindaki diger Python surumlerine dokunulmaz.
set "PYSETUP=%TEMP%\python-3.12.10-amd64.exe"
set "PYURL=https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
if exist "%PYSETUP%" del "%PYSETUP%" >nul 2>&1
curl -L --fail -o "%PYSETUP%" "%PYURL%"
if not exist "%PYSETUP%" powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest '%PYURL%' -OutFile '%PYSETUP%'"
if not exist "%PYSETUP%" (
  echo        Indirme basarisiz. Internet baglantini kontrol et.
  exit /b 1
)
echo        Kuruluyor, lutfen bekle (1-2 dakika)...
"%PYSETUP%" /quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 Include_test=0 Include_doc=0 Shortcuts=0 TargetDir="%LocalAppData%\Programs\Python\Python312"
del "%PYSETUP%" >nul 2>&1
if exist "%PY312%" set "PY="%PY312%""
if defined PY echo        Python 3.12 kuruldu.
exit /b 0

:nopython
echo.
echo  [HATA] Python 3.12 otomatik kurulamadi.
echo  Elle kur: https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe
echo  Kurarken "Add python.exe to PATH" kutusunu isaretle, sonra build.bat'i tekrar calistir.
goto :end

:fail
echo.
echo  [HATA] Derleme yarida kaldi. Yukaridaki son satirlarin ekran goruntusunu gonder.
goto :end

:end
echo.
pause
endlocal
