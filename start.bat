@echo off
cd /d "%~dp0"

if not exist venv (
    echo Buscando Python 3.12...
    py -3.12 --version >nul 2>&1
    if errorlevel 1 (
        echo.
        echo ERROR: Necesitas Python 3.12
        echo Descargalo en: https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe
        echo Durante la instalacion marca "Add Python to PATH"
        echo.
        pause
        exit /b 1
    )
    echo Creando entorno virtual con Python 3.12...
    py -3.12 -m venv venv
    echo Instalando dependencias...
    venv\Scripts\pip install --upgrade pip -q
    venv\Scripts\pip install -r requirements.txt -q
    echo Inicializando base de datos...
    venv\Scripts\python -c "from app.db.base import Base; from app.db.session import engine; Base.metadata.create_all(bind=engine)"
    echo Cargando datos de prueba...
    venv\Scripts\python -m app.db.seed
)

echo.
echo  App:      http://localhost:8000
echo  API Docs: http://localhost:8000/api/v1/docs
echo.
set DEMO_PASSWORD=
for /f "tokens=1,* delims==" %%A in ('findstr /b "DEFAULT_USER_PASSWORD=" .env 2^>nul') do set DEMO_PASSWORD=%%B
if "%DEMO_PASSWORD%"=="" set DEMO_PASSWORD=contecflow2024!
echo  admin       / %DEMO_PASSWORD%
echo  ana.torres  / %DEMO_PASSWORD%
echo  luis.vega   / %DEMO_PASSWORD%
echo  rrhh        / %DEMO_PASSWORD%
echo.
echo  Pulsa Ctrl+C para parar
echo.
if "%LOG_LEVEL%"=="" set LOG_LEVEL=info
venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level %LOG_LEVEL%
pause
