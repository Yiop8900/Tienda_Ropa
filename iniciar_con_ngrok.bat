@echo off
setlocal EnableExtensions
title Tienda Ropa + ngrok
cd /d "%~dp0"

echo.
echo  ==========================================
echo   TIENDA ROPA - Iniciando con ngrok...
echo  ==========================================
echo.

REM =====================================================
REM CONFIGURACION
REM =====================================================

set "PORT=5000"
set "NGROK=C:\ngrok\ngrok.exe"
set "NGROK_API=http://127.0.0.1:4040/api/tunnels"
set "URL_FILE=%TEMP%\ngrok_url.txt"

REM =====================================================
REM VERIFICAR PYTHON
REM =====================================================

set "PYTHON_EXE="
set "PYTHON_ARGS="

where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=py"
    set "PYTHON_ARGS=-3"
    goto PYTHON_OK
)

where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=python"
    set "PYTHON_ARGS="
    goto PYTHON_OK
)

if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe"
    set "PYTHON_ARGS="
    goto PYTHON_OK
)

echo  ERROR: Python no fue encontrado.
echo.
pause
exit /b 1

:PYTHON_OK

echo  Python detectado:
"%PYTHON_EXE%" %PYTHON_ARGS% --version
echo.

REM =====================================================
REM VERIFICAR NGROK
REM =====================================================

if not exist "%NGROK%" (
    echo  ERROR: ngrok no fue encontrado en:
    echo  %NGROK%
    echo.
    echo  Debes tener ngrok.exe en C:\ngrok\ngrok.exe
    echo.
    pause
    exit /b 1
)

echo  ngrok detectado:
"%NGROK%" version
echo.

REM =====================================================
REM INSTALAR DEPENDENCIAS
REM =====================================================

if exist "requirements.txt" (
    echo  Instalando/verificando dependencias...
    "%PYTHON_EXE%" %PYTHON_ARGS% -m pip install -r requirements.txt -q

    if errorlevel 1 (
        echo.
        echo  ERROR: No se pudieron instalar las dependencias.
        echo.
        pause
        exit /b 1
    )
) else (
    echo  ADVERTENCIA: No se encontro requirements.txt. Se continua igual.
)

echo.

REM =====================================================
REM CERRAR NGROK ANTERIOR
REM =====================================================

echo  Cerrando procesos anteriores de ngrok, si existen...
taskkill /IM ngrok.exe /F >nul 2>&1

REM =====================================================
REM LIMPIAR ARCHIVO TEMPORAL
REM =====================================================

if exist "%URL_FILE%" del "%URL_FILE%" >nul 2>&1

REM =====================================================
REM INICIAR NGROK
REM =====================================================

echo  Iniciando ngrok en puerto %PORT%...
start "ngrok - Tienda Ropa" /min "%NGROK%" http %PORT%

echo  Esperando URL publica de ngrok...
set "TRIES=0"
set "NGROK_URL="

:WAIT_NGROK
set /a TRIES+=1

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; try { $r = Invoke-RestMethod 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 2; foreach ($t in $r.tunnels) { if ($t.proto -eq 'https') { Write-Output $t.public_url; break } } } catch { }" > "%URL_FILE%" 2>nul

set "NGROK_URL="
set /p NGROK_URL=<"%URL_FILE%" 2>nul

echo %NGROK_URL% | findstr /B /I "https://" >nul
if not errorlevel 1 goto GOT_NGROK_URL

if %TRIES% GEQ 30 goto NGROK_ERROR

timeout /t 1 /nobreak >nul
goto WAIT_NGROK

:GOT_NGROK_URL

del "%URL_FILE%" >nul 2>&1

REM =====================================================
REM CONFIGURAR URL PUBLICA PARA FLASK / MERCADOPAGO
REM =====================================================

set "MP_BASE_URL=%NGROK_URL%"
set "BASE_URL=%NGROK_URL%"
set "PUBLIC_URL=%NGROK_URL%"
set "FLASK_RUN_PORT=%PORT%"

echo.
echo  ==========================================
echo   TIENDA ROPA INICIADA CON NGROK
echo  ==========================================
echo.
echo   URL publica:
echo   %NGROK_URL%
echo.
echo   Tienda:
echo   %NGROK_URL%
echo.
echo   Admin:
echo   %NGROK_URL%/admin
echo.
echo   Local:
echo   http://127.0.0.1:%PORT%
echo.
echo   Usuario admin : admin
echo   Contrasena    : admin123
echo.
echo   MercadoPago debe redirigir a:
echo   %MP_BASE_URL%
echo.
echo  ==========================================
echo.
echo  IMPORTANTE:
echo  Usa la URL de ngrok, no localhost, para probar pagos y redirecciones.
echo.
echo  Presiona Ctrl+C para detener Flask.
echo  Cierra la ventana de ngrok si quieres detener el tunel.
echo.

start "" "%NGROK_URL%"

REM =====================================================
REM INICIAR FLASK
REM =====================================================

"%PYTHON_EXE%" %PYTHON_ARGS% app.py

echo.
echo  Flask se detuvo.
pause
exit /b 0

:NGROK_ERROR

del "%URL_FILE%" >nul 2>&1

echo.
echo  ERROR: No se pudo obtener la URL publica de ngrok.
echo.
echo  Revisa esto:
echo.
echo  1. Que ngrok tenga version nueva:
echo     "%NGROK%" version
echo.
echo  2. Que tengas authtoken configurado:
echo     "%NGROK%" config add-authtoken TU_TOKEN
echo.
echo  3. Que ngrok haya iniciado bien:
echo     Abre http://127.0.0.1:4040 en el navegador
echo.
pause
exit /b 1