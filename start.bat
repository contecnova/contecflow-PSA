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
echo  admin       / clarive2024!
echo  ana.torres  / clarive2024!
echo  luis.vega   / clarive2024!
echo  rrhh        / clarive2024!
echo.
echo  Pulsa Ctrl+C para parar
echo.
if "%LOG_LEVEL%"=="" set LOG_LEVEL=info
venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level %LOG_LEVEL%
pause
