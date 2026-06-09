@echo off
title Tienda Ropa
cd /d "%~dp0"

set PYTHON=%LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe

echo.
echo  ==========================================
 echo   TIENDA ROPA - Iniciando aplicacion...
echo  ==========================================
echo.

echo  Instalando dependencias...
"%PYTHON%" -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo  ERROR: No se pudo instalar dependencias.
    echo  Asegurate de tener Python instalado.
    pause
    exit /b
)

echo  Dependencias OK.
echo.
echo  ==========================================
echo   Abre tu navegador en:
echo     Tienda :  http://localhost:5000
echo     Admin  :  http://localhost:5000/admin
echo.
echo   Usuario admin : admin
echo   Contrasena    : admin123
echo  ==========================================
echo.
echo  (Presiona Ctrl+C para detener el servidor)
echo.

"%PYTHON%" app.py
pause
