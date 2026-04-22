@echo off
setlocal EnableDelayedExpansion

:: Contecflow - Script de instalación para Windows
:: Uso:
::   setup.bat          - instala todo y arranca
::   setup.bat start    - solo arranca
::   setup.bat stop     - para los servicios
::   setup.bat update   - actualiza dependencias

set BACKEND_PORT=8000
set FRONTEND_PORT=3000
set SCRIPT_DIR=%~dp0
set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║                                          ║
echo  ║   CONTECFLOW                             ║
echo  ║   Professional Services Automation       ║
echo  ║                                          ║
echo  ╚══════════════════════════════════════════╝
echo  contecflow2024! — Plataforma PSA Enterprise
echo.

if "%1"=="start"  goto :start_only
if "%1"=="stop"   goto :stop_services
if "%1"=="update" goto :update_mode

goto :full_install

:full_install
call :setup_backend
if errorlevel 1 goto :error
call :setup_frontend
if errorlevel 1 goto :error
call :start_services
goto :end

:start_only
echo [INFO] Modo: solo arrancar
call :start_services
goto :end

:update_mode
echo [INFO] Modo: actualizar dependencias
call :setup_backend
if errorlevel 1 goto :error
call :setup_frontend
if errorlevel 1 goto :error
echo.
echo [OK] Actualización completada. Ejecuta: setup.bat start
goto :end

:: -----------------------------------------------------------------------
:setup_backend
echo.
echo [PASO 1/3] Configurando backend...
cd /d "%SCRIPT_DIR%"

:: Buscar Python 3.10+
set PYTHON=
for %%p in (py python3.12 python3.11 python3.10 python3 python) do (
    where %%p >nul 2>&1
    if not errorlevel 1 (
        for /f "tokens=*" %%v in ('%%p -c "import sys; v=sys.version_info; print(v.major*100+v.minor)" 2^>nul') do (
            if %%v GEQ 310 (
                if "!PYTHON!"=="" set PYTHON=%%p
            )
        )
    )
)

if "!PYTHON!"=="" (
    echo [WARN] Python 3.10+ no encontrado. Descargando Python 3.12...
    set PY_URL=https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe
    set PY_INSTALLER=%TEMP%\python312.exe
    curl -L -o "!PY_INSTALLER!" "!PY_URL!"
    if errorlevel 1 (
        echo [ERROR] No se pudo descargar Python. Instálalo manualmente desde https://python.org
        exit /b 1
    )
    "!PY_INSTALLER!" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    del "!PY_INSTALLER!" >nul 2>&1
    set PYTHON=python
)

echo [INFO] Python encontrado: !PYTHON!
!PYTHON! --version

:: Crear entorno virtual
if not exist ".venv" (
    echo [INFO] Creando entorno virtual...
    !PYTHON! -m venv .venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual
        exit /b 1
    )
)

echo [INFO] Instalando dependencias Python...
.venv\Scripts\python -m ensurepip --upgrade >nul 2>&1
.venv\Scripts\python -m pip install --quiet --upgrade pip || (
    echo [WARN] No se pudo actualizar pip directamente. Reinstalando pip desde ensurepip...
    .venv\Scripts\python -m ensurepip --default-pip >nul 2>&1 || (
        echo [ERROR] No se pudo instalar pip. Abortando.
        exit /b 1
    )
    .venv\Scripts\python -m pip install --quiet --upgrade pip || (
        echo [ERROR] No se pudo actualizar pip tras ensurepip.
        exit /b 1
    )
)
.venv\Scripts\python -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo al instalar dependencias
    exit /b 1
)

:: Crear .env si no existe
if not exist ".env" (
    echo [INFO] Creando archivo .env...
    for /f "delims=" %%S in ('powershell -NoProfile -Command "[System.BitConverter]::ToString([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).Replace('-','').ToLower()"') do set "SECRET_KEY=%%S"
    for /f "delims=" %%S in ('powershell -NoProfile -Command "[System.BitConverter]::ToString([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).Replace('-','').ToLower()"') do set "CLIENT_PORTAL_SECRET=%%S"
    (
        echo DATABASE_URL=sqlite:///./contecflow.db
        echo SECRET_KEY=!SECRET_KEY!
        echo CLIENT_PORTAL_SECRET=!CLIENT_PORTAL_SECRET!
        echo ACCESS_TOKEN_EXPIRE_MINUTES=60
        echo REFRESH_TOKEN_EXPIRE_DAYS=30
        echo ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:5173","http://localhost:8000"]
        echo SUPERADMIN_EMAIL=admin@company.com
        echo SUPERADMIN_PASSWORD=contecflow2024!
        echo DEFAULT_USER_PASSWORD=contecflow2024!
        echo ANTHROPIC_API_KEY=
        echo CONTECFLOW_AI_MODEL=claude-haiku-4-5
    ) > .env
    echo [INFO] Archivo .env creado. Edita ANTHROPIC_API_KEY para activar la IA completa.
)

:: Patch existing .env: ensure required variables are present
findstr /b "CLIENT_PORTAL_SECRET=" .env >nul 2>&1
if errorlevel 1 (
    echo [WARN] CLIENT_PORTAL_SECRET no encontrado en .env - añadiendo valor por defecto
    echo CLIENT_PORTAL_SECRET=contecflow-portal-secret-change-in-production!! >> .env
)
findstr /b "SECRET_KEY=" .env >nul 2>&1
if errorlevel 1 (
    echo [WARN] SECRET_KEY no encontrado en .env - añadiendo valor por defecto
    echo SECRET_KEY=contecflow-secret-key-change-in-production-min32chars!! >> .env
)
findstr /b "SUPERADMIN_EMAIL=" .env >nul 2>&1
if errorlevel 1 (
    echo [WARN] SUPERADMIN_EMAIL no encontrado en .env - añadiendo valor por defecto
    echo SUPERADMIN_EMAIL=admin@company.com >> .env
)
findstr /b "SUPERADMIN_PASSWORD=" .env >nul 2>&1
if errorlevel 1 (
    echo [WARN] SUPERADMIN_PASSWORD no encontrado en .env - añadiendo valor por defecto
    echo SUPERADMIN_PASSWORD=contecflow2024! >> .env
)
findstr /b "DEFAULT_USER_PASSWORD=" .env >nul 2>&1
if errorlevel 1 (
    echo [WARN] DEFAULT_USER_PASSWORD no encontrado en .env - añadiendo valor por defecto
    echo DEFAULT_USER_PASSWORD=contecflow2024! >> .env
)

echo [INFO] Aplicando migraciones de base de datos...
.venv\Scripts\python -m app.db.migrate

:: Comprobar si la BD tiene usuarios
for /f "tokens=*" %%r in ('.venv\Scripts\python -c "from app.db.session import SessionLocal; from app.models.user import User; db=SessionLocal(); c=db.query(User).filter(User.hashed_password!=None).count(); db.close(); print('ok' if c>0 else 'empty')" 2^>nul') do set DB_STATUS=%%r

if "!DB_STATUS!"=="empty" (
    echo [INFO] Base de datos vacía - ejecutando seed...
    del /f contecflow.db >nul 2>&1
    .venv\Scripts\python -m app.db.migrate
    .venv\Scripts\python -m app.db.seed
) else if "!DB_STATUS!"=="ok" (
    echo [INFO] Base de datos OK - datos existentes conservados
) else (
    echo [INFO] Inicializando base de datos nueva...
    del /f contecflow.db >nul 2>&1
    .venv\Scripts\python -m app.db.migrate
    .venv\Scripts\python -m app.db.seed
)

call :sync_demo_passwords

exit /b 0

:: -----------------------------------------------------------------------
:setup_frontend
echo.
echo [PASO 2/3] Configurando frontend...
cd /d "%SCRIPT_DIR%"

where node >nul 2>&1
if errorlevel 1 (
    echo [WARN] Node.js no encontrado. Descargando Node.js LTS...
    set NODE_URL=https://nodejs.org/dist/v20.11.0/node-v20.11.0-x64.msi
    set NODE_INSTALLER=%TEMP%\nodejs.msi
    curl -L -o "!NODE_INSTALLER!" "!NODE_URL!"
    if errorlevel 1 (
        echo [ERROR] No se pudo descargar Node.js. Instálalo desde https://nodejs.org
        exit /b 1
    )
    msiexec /i "!NODE_INSTALLER!" /quiet /norestart
    del "!NODE_INSTALLER!" >nul 2>&1
    echo [INFO] Node.js instalado. Si hay errores, reinicia el terminal.
)

for /f "tokens=*" %%v in ('node --version 2^>nul') do echo [INFO] Node.js %%v
for /f "tokens=*" %%v in ('npm --version 2^>nul') do echo [INFO] npm %%v

cd /d "%SCRIPT_DIR%\frontend"
if not exist "node_modules" (
    echo [INFO] Instalando dependencias npm ^(puede tardar unos minutos^)...
    npm install --no-fund --no-audit --prefer-offline --legacy-peer-deps
    if errorlevel 1 (
        echo [ERROR] Fallo npm install
        exit /b 1
    )
) else (
    if not exist "node_modules\vite\dist\node\cli.js" (
        echo [WARN] Vite no encontrado en node_modules. Reinstalando dependencias...
        npm install --no-fund --no-audit --prefer-offline --legacy-peer-deps
        if errorlevel 1 (
            echo [ERROR] Fallo npm install
            exit /b 1
        )
    ) else (
        echo [INFO] node_modules ya existe - omitiendo instalación
    )
)

cd /d "%SCRIPT_DIR%"
exit /b 0

:: -----------------------------------------------------------------------
:start_services
echo.
echo [PASO 3/3] Arrancando servicios...
cd /d "%SCRIPT_DIR%"

if not exist ".venv\Scripts\python.exe" (
    echo [WARN] Entorno virtual no encontrado. Inicializando backend automáticamente...
    call :setup_backend
    if errorlevel 1 exit /b 1
)

if not exist "%SCRIPT_DIR%\frontend\node_modules\vite\dist\node\cli.js" (
    echo [WARN] Frontend no preparado. Inicializando frontend automáticamente...
    call :setup_frontend
    if errorlevel 1 exit /b 1
)

:: Always sync demo passwords before starting -- ensures hash matches .env even on 'start only'
call :sync_demo_passwords

:: Matar procesos en los puertos si ya existen
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%BACKEND_PORT% " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%FRONTEND_PORT% " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

:: Arrancar backend
echo [INFO] Arrancando backend en puerto %BACKEND_PORT%...
start "Contecflow Backend" /min cmd /c "cd /d \"%SCRIPT_DIR%\" && .venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT% --log-level info > \"%TEMP%\contecflow-backend.log\" 2>&1"

:: Esperar a que el backend responda (máx. 60 s)
echo [INFO] Esperando backend
set BACKEND_ATTEMPTS=0
:wait_backend
set /a BACKEND_ATTEMPTS+=1
if %BACKEND_ATTEMPTS% GTR 60 (
    echo [ERROR] El backend no respondio en 60 segundos.
    echo [ERROR] Revisa los logs: %TEMP%\contecflow-backend.log
    exit /b 1
)
timeout /t 1 /nobreak >nul
curl -s http://localhost:%BACKEND_PORT%/health >nul 2>&1
if errorlevel 1 goto :wait_backend
echo [INFO] Backend listo

:: Arrancar frontend
echo [INFO] Arrancando frontend en puerto %FRONTEND_PORT%...
start "Contecflow Frontend" /min cmd /c "cd /d \"%SCRIPT_DIR%\frontend\" && npm run dev -- --port %FRONTEND_PORT% > \"%TEMP%\contecflow-frontend.log\" 2>&1"

:: Esperar frontend (máx. 60 s)
echo [INFO] Esperando frontend
set FRONTEND_ATTEMPTS=0
:wait_frontend
set /a FRONTEND_ATTEMPTS+=1
if %FRONTEND_ATTEMPTS% GTR 60 (
    echo [ERROR] El frontend no respondio en 60 segundos.
    echo [ERROR] Revisa los logs: %TEMP%\contecflow-frontend.log
    exit /b 1
)
timeout /t 1 /nobreak >nul
curl -s http://localhost:%FRONTEND_PORT% >nul 2>&1
if errorlevel 1 goto :wait_frontend
echo [INFO] Frontend listo

echo.
echo ╔══════════════════════════════════════════╗
echo ║         Contecflow listo ✓              ║
echo ╚══════════════════════════════════════════╝
echo.
echo   🌐 App:      http://localhost:%FRONTEND_PORT%
echo   📡 API:      http://localhost:%BACKEND_PORT%/api/v1/docs
echo   📋 Logs:     %TEMP%\contecflow-backend.log
echo.
call :get_demo_password
echo   Usuarios de prueba:
echo     admin      / !DEMO_PASSWORD!   → Dirección
echo     ana.torres / !DEMO_PASSWORD!   → PM
echo     luis.vega  / !DEMO_PASSWORD!   → Empleado
echo     rrhh       / !DEMO_PASSWORD!   → RRHH
echo.
echo   Para parar:  setup.bat stop
echo.

timeout /t 2 /nobreak >nul
start "" "http://localhost:%FRONTEND_PORT%"

echo Presiona cualquier tecla para cerrar esta ventana...
echo ^(Los servicios continúan en segundo plano^)
pause >nul
goto :end

:: -----------------------------------------------------------------------
:stop_services
echo [INFO] Parando Contecflow...
taskkill /FI "WINDOWTITLE eq Contecflow Backend*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Contecflow Frontend*" /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%BACKEND_PORT% " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%FRONTEND_PORT% " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo [OK] Servicios parados.
goto :end

:: -----------------------------------------------------------------------
:get_demo_password
set "DEMO_PASSWORD="
for /f "tokens=1,* delims==" %%A in ('findstr /b "DEFAULT_USER_PASSWORD=" .env 2^>nul') do set "DEMO_PASSWORD=%%B"
if "!DEMO_PASSWORD!"=="" set "DEMO_PASSWORD=contecflow2024!"
exit /b 0

:: -----------------------------------------------------------------------
:sync_demo_passwords
setlocal EnableDelayedExpansion
call :get_demo_password
set "DEMO_PWD=!DEMO_PASSWORD!"

:: Compute a simple sentinel: write password to tmp, hash it if certutil available
set "PWD_HASH_FILE=.venv\.pwd_hash"
set "CURRENT_HASH=!DEMO_PWD!"

if exist "%PWD_HASH_FILE%" (
    set /p STORED_HASH=<"%PWD_HASH_FILE%"
    if "!STORED_HASH!"=="!CURRENT_HASH!" (
        echo [INFO] Contraseñas demo sin cambios, omitiendo rehash
        endlocal
        exit /b 0
    )
)

echo [INFO] Sincronizando contraseñas demo con DEFAULT_USER_PASSWORD...
.venv\Scripts\python -c "from app.db.session import SessionLocal; from app.models.user import User; from app.core.security import get_password_hash; db=SessionLocal(); [setattr(u,'hashed_password',get_password_hash('!DEMO_PWD!')) for u in db.query(User).filter(User.username.in_(['admin','ana.torres','luis.vega','rrhh'])).all()]; db.commit(); db.close(); print('ok')"
if errorlevel 1 (
    echo [WARN] No se pudieron sincronizar las contraseñas demo automáticamente
) else (
    echo !CURRENT_HASH!> "%PWD_HASH_FILE%"
    echo [INFO] Contraseñas actualizadas correctamente
)
endlocal
exit /b 0

:: -----------------------------------------------------------------------
:error
echo.
echo [ERROR] La instalación ha fallado.
echo Comprueba los mensajes anteriores para ver el problema.
echo.
pause
exit /b 1

:end
endlocal
