@echo off
setlocal EnableDelayedExpansion

:: Contecflow - Script de instalación para Windows
:: Uso:
::   setup.bat          - instala todo y arranca
::   setup.bat start    - solo arranca
::   setup.bat start demo^|clean - solo arranca con modo de datos
::   setup.bat demo^|clean - instala y arranca con modo de datos
::   setup.bat stop     - para los servicios
::   setup.bat update   - actualiza dependencias
::   SETUP_INIT_MODE=demo^|clean setup.bat start  - modo no interactivo (CI/CD)

set BACKEND_PORT=8000
set FRONTEND_PORT=3000
set SCRIPT_DIR=%~dp0
set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%
set REQUESTED_MODE=
set INIT_MODE=

echo.
echo  ============================================
echo    CONTECFLOW
echo    Professional Services Automation
echo  ============================================
echo  contecflow2024^! - Plataforma PSA Enterprise
echo.

if "%1"=="start"  goto :start_only
if "%1"=="stop"   goto :stop_services
if "%1"=="update" goto :update_mode

if /I "%1"=="demo"  set "REQUESTED_MODE=demo"
if /I "%1"=="seed"  set "REQUESTED_MODE=demo"
if /I "%1"=="clean" set "REQUESTED_MODE=clean"
if /I "%1"=="zero"  set "REQUESTED_MODE=clean"
if /I "%1"=="cero"  set "REQUESTED_MODE=clean"
if /I "%1"=="admin-only" set "REQUESTED_MODE=clean"
if /I "%1"=="admin_only" set "REQUESTED_MODE=clean"

goto :full_install

:full_install
call :setup_backend
if errorlevel 1 goto :error
call :setup_frontend
if errorlevel 1 goto :error
call :resolve_init_mode "%REQUESTED_MODE%"
if errorlevel 1 goto :error
call :apply_selected_data_mode
if errorlevel 1 goto :error
call :start_services
goto :end

:start_only
echo [INFO] Modo: solo arrancar
set "REQUESTED_MODE=%2"
if not exist "%SCRIPT_DIR%\.venv\Scripts\python.exe" (
    call :setup_backend
    if errorlevel 1 goto :error
)
if not exist "%SCRIPT_DIR%\frontend\node_modules\vite\dist\node\cli.js" (
    call :setup_frontend
    if errorlevel 1 goto :error
)
call :resolve_init_mode "%REQUESTED_MODE%"
if errorlevel 1 goto :error
call :apply_selected_data_mode
if errorlevel 1 goto :error
call :start_services
goto :end

:update_mode
echo [INFO] Modo: actualizar dependencias
call :setup_backend
if errorlevel 1 goto :error
call :setup_frontend
if errorlevel 1 goto :error
echo.
echo [OK] Actualizacion completada. Ejecuta: setup.bat start
goto :end

:: -----------------------------------------------------------------------
:resolve_init_mode
set "INIT_MODE="
set "RAW_MODE=%~1"

if "%RAW_MODE%"=="" set "RAW_MODE=%SETUP_INIT_MODE%"

if /I "%RAW_MODE%"=="demo" set "INIT_MODE=demo"
if /I "%RAW_MODE%"=="seed" set "INIT_MODE=demo"
if /I "%RAW_MODE%"=="clean" set "INIT_MODE=clean"
if /I "%RAW_MODE%"=="zero" set "INIT_MODE=clean"
if /I "%RAW_MODE%"=="cero" set "INIT_MODE=clean"
if /I "%RAW_MODE%"=="admin-only" set "INIT_MODE=clean"
if /I "%RAW_MODE%"=="admin_only" set "INIT_MODE=clean"

if "%RAW_MODE%"=="" goto :ask_init_mode

if not "%INIT_MODE%"=="" exit /b 0

echo [ERROR] Modo de inicializacion invalido: %RAW_MODE% ^(usa demo^|clean^)
exit /b 1

:ask_init_mode
echo.
echo Inicializacion de datos
echo   1^) demo  - carga datos de demo
echo   2^) clean - base vacia salvo usuario admin
set /p MODE_CHOICE=Elige [1/2] (default 1): 
if "%MODE_CHOICE%"=="2" (
    set "INIT_MODE=clean"
) else (
    set "INIT_MODE=demo"
)
exit /b 0

:: -----------------------------------------------------------------------
:apply_selected_data_mode
if /I "%INIT_MODE%"=="clean" goto :prepare_admin_only_database
if /I "%INIT_MODE%"=="demo"  goto :prepare_demo_database
echo [ERROR] INIT_MODE no soportado: %INIT_MODE%
exit /b 1

:: -----------------------------------------------------------------------
:prepare_demo_database
echo.
echo [INFO] Inicializando base de datos con datos demo...
cd /d "%SCRIPT_DIR%"
.venv\Scripts\python -m app.db.seed
if errorlevel 1 (
        echo [ERROR] Fallo al cargar datos demo
        exit /b 1
)
echo [OK] Datos demo cargados
exit /b 0

:: -----------------------------------------------------------------------
:prepare_admin_only_database
echo.
echo [INFO] Reseteando base de datos ^(solo admin^) ...
cd /d "%SCRIPT_DIR%"
.venv\Scripts\python scripts\reset_to_admin_only.py
if errorlevel 1 (
        echo [ERROR] Fallo al resetear base de datos a modo clean
        exit /b 1
)
echo [OK] Base de datos limpia con solo admin
exit /b 0

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
    if errorlevel 1 (
        echo [ERROR] No se pudo instalar Python automáticamente.
        echo [ERROR] Instálalo manualmente desde https://www.python.org/downloads/ y reinicia el terminal.
        del "!PY_INSTALLER!" >nul 2>&1
        exit /b 1
    )
    del "!PY_INSTALLER!" >nul 2>&1
    set PYTHON=python

    where !PYTHON! >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python se instaló, pero no está en PATH en esta sesión.
        echo [ERROR] Cierra y abre el terminal, o instala manualmente desde https://www.python.org/downloads/
        exit /b 1
    )

    for /f "tokens=*" %%v in ('!PYTHON! -c "import sys; v=sys.version_info; print(v.major*100+v.minor)" 2^>nul') do set PY_VER_NUM=%%v
    if not defined PY_VER_NUM (
        echo [ERROR] No se pudo verificar la versión de Python tras la instalación.
        exit /b 1
    )
    if !PY_VER_NUM! LSS 310 (
        echo [ERROR] Python detectado no cumple versión mínima 3.10+.
        echo [ERROR] Instala manualmente una versión compatible desde https://www.python.org/downloads/
        exit /b 1
    )
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

set "REQ_HASH_FILE=.venv\.req_hash"
set "REQ_HASH="
for /f "delims=" %%H in ('powershell -NoProfile -Command "if(Test-Path 'requirements.txt'){ (Get-FileHash -Algorithm SHA256 -Path 'requirements.txt').Hash.ToLower() }"') do set "REQ_HASH=%%H"

set "NEED_PIP_INSTALL=1"
if exist "!REQ_HASH_FILE!" (
    set /p STORED_REQ_HASH=<"!REQ_HASH_FILE!"
    if /I "!STORED_REQ_HASH!"=="!REQ_HASH!" set "NEED_PIP_INSTALL=0"
)

if "!NEED_PIP_INSTALL!"=="1" (
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
    >"!REQ_HASH_FILE!" echo !REQ_HASH!
) else (
    echo [INFO] Dependencias Python sin cambios, omitiendo pip install
)

if exist "requirements-ml.txt" (
    set "REQ_ML_HASH_FILE=.venv\.req_ml_hash"
    set "REQ_ML_HASH="
    for /f "delims=" %%H in ('powershell -NoProfile -Command "if(Test-Path 'requirements-ml.txt'){ (Get-FileHash -Algorithm SHA256 -Path 'requirements-ml.txt').Hash.ToLower() }"') do set "REQ_ML_HASH=%%H"

    set "NEED_ML_INSTALL=1"
    if exist "!REQ_ML_HASH_FILE!" (
        set /p STORED_REQ_ML_HASH=<"!REQ_ML_HASH_FILE!"
        if /I "!STORED_REQ_ML_HASH!"=="!REQ_ML_HASH!" set "NEED_ML_INSTALL=0"
    )

    if "!NEED_ML_INSTALL!"=="1" (
        echo [INFO] Instalando dependencias ML ^(requirements-ml.txt^)...
        .venv\Scripts\python -m pip install --quiet -r requirements-ml.txt
        if errorlevel 1 (
            echo [ERROR] Fallo al instalar dependencias ML
            exit /b 1
        )
        >"!REQ_ML_HASH_FILE!" echo !REQ_ML_HASH!
    ) else (
        echo [INFO] Dependencias ML sin cambios, omitiendo pip install
    )
)

:: Dependencias opcionales: CMDB auto-discovery (boto3=AWS, kubernetes=K8s)
:: Se instalan solo si requirements-discovery.txt existe o si hay vars AWS/K8s en .env
if exist "requirements-discovery.txt" (
    echo [INFO] Instalando dependencias opcionales de CMDB discovery...
    .venv\Scripts\python -m pip install --quiet -r requirements-discovery.txt
    if errorlevel 1 (
        echo [WARN] Algunas dependencias opcionales de discovery no se pudieron instalar ^(no es bloqueante^)
    )
) else (
    :: Comprobar si AWS está configurado en .env
    findstr /R /C:"^AWS_ACCESS_KEY_ID=." .env >nul 2>&1
    if not errorlevel 1 (
        echo [INFO] AWS configurado - instalando boto3...
        .venv\Scripts\python -m pip install --quiet boto3 || echo [WARN] No se pudo instalar boto3
    )
    :: Comprobar si Kubernetes está configurado en .env
    findstr /R /C:"^KUBECONFIG=." .env >nul 2>&1
    if not errorlevel 1 (
        echo [INFO] Kubernetes configurado - instalando kubernetes client...
        .venv\Scripts\python -m pip install --quiet kubernetes || echo [WARN] No se pudo instalar kubernetes client
    )
    findstr /R /C:"^K8S_IN_CLUSTER=true" .env >nul 2>&1
    if not errorlevel 1 (
        echo [INFO] K8s in-cluster configurado - instalando kubernetes client...
        .venv\Scripts\python -m pip install --quiet kubernetes || echo [WARN] No se pudo instalar kubernetes client
    )
)

:: Crear .env si no existe
if not exist ".env" (
    echo [INFO] Creando archivo .env...
    for /f "delims=" %%S in ('powershell -NoProfile -Command "[System.BitConverter]::ToString([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).Replace('-','').ToLower()"') do set "SECRET_KEY=%%S"
    for /f "delims=" %%S in ('powershell -NoProfile -Command "[System.BitConverter]::ToString([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).Replace('-','').ToLower()"') do set "CLIENT_PORTAL_SECRET=%%S"
    :: Contraseñas iniciales aleatorias por instalación. Antes eran la constante
    :: 'contecflow2024!', compartida por toda instalación de Contecflow y con el
    :: valor publicado en este script. El resumen final imprime las credenciales
    :: generadas, así que el onboarding local no cambia.
    for /f "delims=" %%S in ('powershell -NoProfile -Command "[System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(15)).Replace('+','x').Replace('/','y').Replace('=','') + 'Aa1!'"') do set "INIT_ADMIN_PWD=%%S"
    for /f "delims=" %%S in ('powershell -NoProfile -Command "[System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(15)).Replace('+','x').Replace('/','y').Replace('=','') + 'Aa1!'"') do set "INIT_USER_PWD=%%S"
    (
        echo DATABASE_URL=sqlite:///./contecflow.db
        echo SECRET_KEY=!SECRET_KEY!
        echo CLIENT_PORTAL_SECRET=!CLIENT_PORTAL_SECRET!
        echo ACCESS_TOKEN_EXPIRE_MINUTES=60
        echo REFRESH_TOKEN_EXPIRE_DAYS=30
        echo ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:5173","http://localhost:8000"]
        echo ENVIRONMENT=development
        echo SUPERADMIN_EMAIL=admin@company.com
        echo SUPERADMIN_PASSWORD=!INIT_ADMIN_PWD!
        echo DEFAULT_USER_PASSWORD=!INIT_USER_PWD!
        echo ANTHROPIC_API_KEY=
        echo CONTECFLOW_AI_MODEL=claude-haiku-4-5
    ) > .env
    echo [INFO] Archivo .env creado. Edita ANTHROPIC_API_KEY para activar la IA completa.
)

:: Patch existing .env: ensure required variables are present
findstr /b "CLIENT_PORTAL_SECRET=" .env >nul 2>&1
if errorlevel 1 (
    echo [WARN] CLIENT_PORTAL_SECRET no encontrado en .env - añadiendo valor por defecto
    echo CLIENT_PORTAL_SECRET=contecflow-portal-secret-change-in-production^!^! >> .env
)
findstr /b "SECRET_KEY=" .env >nul 2>&1
if errorlevel 1 (
    echo [WARN] SECRET_KEY no encontrado en .env - añadiendo valor por defecto
    echo SECRET_KEY=contecflow-secret-key-change-in-production-min32chars^!^! >> .env
)
findstr /b "SUPERADMIN_EMAIL=" .env >nul 2>&1
if errorlevel 1 (
    echo [WARN] SUPERADMIN_EMAIL no encontrado en .env - añadiendo valor por defecto
    echo SUPERADMIN_EMAIL=admin@company.com >> .env
)
findstr /b "SUPERADMIN_PASSWORD=" .env >nul 2>&1
if errorlevel 1 (
    echo [WARN] SUPERADMIN_PASSWORD no encontrado en .env - generando una aleatoria
    for /f "delims=" %%S in ('powershell -NoProfile -Command "[System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(15)).Replace('+','x').Replace('/','y').Replace('=','') + 'Aa1!'"') do echo SUPERADMIN_PASSWORD=%%S >> .env
)
findstr /b "DEFAULT_USER_PASSWORD=" .env >nul 2>&1
if errorlevel 1 (
    echo [WARN] DEFAULT_USER_PASSWORD no encontrado en .env - generando una aleatoria
    for /f "delims=" %%S in ('powershell -NoProfile -Command "[System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(15)).Replace('+','x').Replace('/','y').Replace('=','') + 'Aa1!'"') do echo DEFAULT_USER_PASSWORD=%%S >> .env
)
:: ENVIRONMENT gobierna el gate de :sync_demo_passwords. Si falta, los scripts
:: asumen production y NO reescriben credenciales.
findstr /b "ENVIRONMENT=" .env >nul 2>&1
if errorlevel 1 (
    echo [INFO] ENVIRONMENT no encontrado en .env - estableciendo development
    echo ENVIRONMENT=development >> .env
)

:: Regenerar SECRET_KEY si quedó con placeholder/insegura
set "SECRET_STATUS="
for /f "delims=" %%S in ('powershell -NoProfile -Command "$p='.env'; if(-not (Test-Path $p)){ Write-Output 'OK'; exit 0 }; $line=(Get-Content $p | Where-Object {$_ -match '^SECRET_KEY='} | Select-Object -Last 1); $v=if($line){$line.Substring(11)} else {''}; $bad=($v.Length -lt 32) -or ($v -match '^(?i:CHANGE_ME|REPLACE_ME)') -or ($v -eq 'contecflow-secret-key-change-in-production-min32chars!!'); if($bad){ $rng=[System.Security.Cryptography.RandomNumberGenerator]::Create(); $bytes=New-Object byte[] 32; $rng.GetBytes($bytes); $new=[System.BitConverter]::ToString($bytes).Replace('-','').ToLower(); $content=Get-Content $p; $seen=$false; $content=$content | ForEach-Object { if($_ -match '^SECRET_KEY='){ $seen=$true; 'SECRET_KEY='+$new } else { $_ } }; if(-not $seen){ $content += 'SECRET_KEY='+$new }; Set-Content -Path $p -Value $content -Encoding ASCII; Write-Output 'ROTATED' } else { Write-Output 'OK' }"') do set "SECRET_STATUS=%%S"
if /I "!SECRET_STATUS!"=="ROTATED" (
    echo [WARN] SECRET_KEY insegura detectada en .env - regenerada automaticamente
)

set "MODELS_HASH_FILE=.venv\.models_hash"
set "MODELS_HASH="
for /f "delims=" %%H in ('powershell -NoProfile -Command "$files=Get-ChildItem -Path 'app/models' -Recurse -Filter '*.py' -File -ErrorAction SilentlyContinue ^| Sort-Object FullName; if(-not $files){ 'nohash'; exit 0 }; $joined=($files ^| ForEach-Object { $h=(Get-FileHash -Algorithm SHA256 -Path $_.FullName).Hash.ToLower(); $_.FullName + '|' + $h }) -join \"`n\"; $bytes=[Text.Encoding]::UTF8.GetBytes($joined); $sha=[Security.Cryptography.SHA256]::Create(); (($sha.ComputeHash($bytes) ^| ForEach-Object { $_.ToString('x2') }) -join '')"') do set "MODELS_HASH=%%H"

set "NEED_MIGRATE=0"
if not exist "contecflow.db" set "NEED_MIGRATE=1"
if not exist "!MODELS_HASH_FILE!" set "NEED_MIGRATE=1"
if exist "!MODELS_HASH_FILE!" (
    set /p STORED_MODELS_HASH=<"!MODELS_HASH_FILE!"
    if /I not "!STORED_MODELS_HASH!"=="!MODELS_HASH!" set "NEED_MIGRATE=1"
)

if "!NEED_MIGRATE!"=="1" (
    echo [INFO] Aplicando migraciones de base de datos...
    .venv\Scripts\python -m app.db.migrate
    if errorlevel 1 (
        echo [ERROR] Fallo al aplicar migraciones.
        echo [ERROR] Revisa tu archivo .env ^(especialmente SECRET_KEY^) y vuelve a ejecutar setup.bat
        exit /b 1
    )
    >"!MODELS_HASH_FILE!" echo !MODELS_HASH!
) else (
    echo [INFO] Modelos sin cambios, omitiendo migracion
)

:: Comprobar si la BD tiene usuarios
for /f "tokens=*" %%r in ('.venv\Scripts\python -c "from app.db.session import SessionLocal; from app.models.user import User; db=SessionLocal(); c=db.query(User).filter(User.hashed_password!=None).count(); db.close(); print('ok' if c>0 else 'empty')" 2^>nul') do set DB_STATUS=%%r

if "!DB_STATUS!"=="empty" (
    echo [INFO] Base de datos vacía - ejecutando seed...
    del /f contecflow.db >nul 2>&1
    .venv\Scripts\python -m app.db.migrate
    if errorlevel 1 (
        echo [ERROR] Fallo al aplicar migraciones durante inicialización de base de datos.
        exit /b 1
    )
    .venv\Scripts\python -m app.db.seed
    if errorlevel 1 (
        echo [ERROR] Fallo al ejecutar seed de base de datos.
        exit /b 1
    )
) else if "!DB_STATUS!"=="ok" (
    echo [INFO] Base de datos OK - datos existentes conservados
) else (
    echo [INFO] Inicializando base de datos nueva...
    del /f contecflow.db >nul 2>&1
    .venv\Scripts\python -m app.db.migrate
    if errorlevel 1 (
        echo [ERROR] Fallo al aplicar migraciones durante inicialización de base de datos.
        exit /b 1
    )
    .venv\Scripts\python -m app.db.seed
    if errorlevel 1 (
        echo [ERROR] Fallo al ejecutar seed de base de datos.
        exit /b 1
    )
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
    if errorlevel 1 (
        echo [ERROR] No se pudo instalar Node.js automáticamente.
        echo [ERROR] Instálalo manualmente desde https://nodejs.org/ y reinicia el terminal.
        del "!NODE_INSTALLER!" >nul 2>&1
        exit /b 1
    )
    del "!NODE_INSTALLER!" >nul 2>&1
    where node >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Node.js se instaló, pero no está en PATH en esta sesión.
        echo [ERROR] Cierra y abre el terminal, o instala manualmente desde https://nodejs.org/
        exit /b 1
    )
    where npm >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] npm no está disponible tras la instalación de Node.js.
        echo [ERROR] Reinstala Node.js desde https://nodejs.org/ y reinicia el terminal.
        exit /b 1
    )
    echo [INFO] Node.js instalado y validado.
)

for /f "tokens=*" %%v in ('node --version 2^>nul') do echo [INFO] Node.js %%v
for /f "tokens=*" %%v in ('npm --version 2^>nul') do echo [INFO] npm %%v

set "NODE_MAJOR="
for /f "delims=" %%V in ('powershell -NoProfile -Command "$v=(node --version 2^>$null); if($v){ [int](($v.TrimStart(\"v\").Split(\".\"))[0]) }"') do set "NODE_MAJOR=%%V"
if defined NODE_MAJOR if !NODE_MAJOR! LSS 18 (
    echo [WARN] Node.js !NODE_MAJOR! detectado. Se recomienda v18+.
)

cd /d "%SCRIPT_DIR%\frontend"
set "PKG_HASH_FILE=node_modules\.pkg_hash"
set "PKG_HASH="
for /f "delims=" %%H in ('powershell -NoProfile -Command "if(Test-Path 'package.json'){ (Get-FileHash -Algorithm SHA256 -Path 'package.json').Hash.ToLower() }"') do set "PKG_HASH=%%H"

set "NEED_NPM_INSTALL=0"
if not exist "node_modules" set "NEED_NPM_INSTALL=1"
if not exist "!PKG_HASH_FILE!" set "NEED_NPM_INSTALL=1"
if exist "!PKG_HASH_FILE!" (
    set /p STORED_PKG_HASH=<"!PKG_HASH_FILE!"
    if /I not "!STORED_PKG_HASH!"=="!PKG_HASH!" set "NEED_NPM_INSTALL=1"
)
if not exist "node_modules\vite\dist\node\cli.js" (
    echo [WARN] Vite no encontrado en node_modules. Ejecutando npm install...
    set "NEED_NPM_INSTALL=1"
)

if "!NEED_NPM_INSTALL!"=="1" (
    echo [INFO] Instalando dependencias npm ^(puede tardar unos minutos^)...
    npm install --no-fund --no-audit --prefer-offline --legacy-peer-deps
    if errorlevel 1 (
        echo [ERROR] Fallo npm install
        exit /b 1
    )
    >"!PKG_HASH_FILE!" echo !PKG_HASH!
) else (
    echo [INFO] Dependencias npm sin cambios, omitiendo npm install
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

:: Liberar puertos antes de arrancar
call :kill_port %BACKEND_PORT%
call :kill_port %FRONTEND_PORT%
call :wait_port_free %BACKEND_PORT% 15
if errorlevel 1 (
    echo [ERROR] El puerto %BACKEND_PORT% sigue ocupado antes de arrancar el backend.
    exit /b 1
)
call :wait_port_free %FRONTEND_PORT% 15
if errorlevel 1 (
    echo [ERROR] El puerto %FRONTEND_PORT% sigue ocupado antes de arrancar el frontend.
    exit /b 1
)

:: Arrancar backend
echo [INFO] Arrancando backend en puerto %BACKEND_PORT%...
set "BACKEND_RUNNER=%TEMP%\contecflow-backend-runner.cmd"
(
    echo @echo off
    echo cd /d "%SCRIPT_DIR%"
    echo .venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT% --log-level info 1^>"%TEMP%\contecflow-backend.log" 2^>"%TEMP%\contecflow-backend.err.log"
) > "%BACKEND_RUNNER%"
start "Contecflow Backend" /min "%COMSPEC%" /c call "%BACKEND_RUNNER%"
if errorlevel 1 (
    echo [ERROR] No se pudo lanzar el backend.
    exit /b 1
)

:: Esperar a que el backend responda (máx. 180 s)
echo [INFO] Esperando backend
set BACKEND_ATTEMPTS=0
:wait_backend
set /a BACKEND_ATTEMPTS+=1
if %BACKEND_ATTEMPTS% GTR 180 (
    echo [ERROR] El backend no respondio en 180 segundos.
    echo [ERROR] Revisa los logs: %TEMP%\contecflow-backend.log y %TEMP%\contecflow-backend.err.log
    exit /b 1
)
curl --silent --fail --connect-timeout 1 --max-time 1 "http://127.0.0.1:%BACKEND_PORT%/health" >nul 2>&1
if NOT "%ERRORLEVEL%"=="0" (
    timeout /t 1 /nobreak >nul
    goto :wait_backend
)
echo [INFO] Backend listo

if not exist "frontend\node_modules" mkdir "frontend\node_modules" >nul 2>&1

set "VITE_HASH="
for /f "delims=" %%H in ('powershell -NoProfile -Command "$files=Get-ChildItem -Path 'frontend/src' -Recurse -File -Include '*.js','*.jsx' -ErrorAction SilentlyContinue ^| Sort-Object FullName; if(-not $files){ 'nohash'; exit 0 }; $joined=($files ^| ForEach-Object { $h=(Get-FileHash -Algorithm SHA256 -Path $_.FullName).Hash.ToLower(); $_.FullName + '|' + $h }) -join \"`n\"; $bytes=[Text.Encoding]::UTF8.GetBytes($joined); $sha=[Security.Cryptography.SHA256]::Create(); (($sha.ComputeHash($bytes) ^| ForEach-Object { $_.ToString('x2') }) -join '')"') do set "VITE_HASH=%%H"
set "VITE_HASH_FILE=frontend\node_modules\.vite_src_hash"
set "REFRESH_VITE_CACHE=0"
if not exist "!VITE_HASH_FILE!" set "REFRESH_VITE_CACHE=1"
if exist "!VITE_HASH_FILE!" (
    set /p STORED_VITE_HASH=<"!VITE_HASH_FILE!"
    if /I not "!STORED_VITE_HASH!"=="!VITE_HASH!" set "REFRESH_VITE_CACHE=1"
)
if "!REFRESH_VITE_CACHE!"=="1" (
    if exist "frontend\node_modules\.vite" rmdir /s /q "frontend\node_modules\.vite" >nul 2>&1
    >"!VITE_HASH_FILE!" echo !VITE_HASH!
)

if exist "frontend\node_modules\@babel\parser\lib\index.js" (
    set "JSX_HASH="
    for /f "delims=" %%H in ('powershell -NoProfile -Command "$files=Get-ChildItem -Path 'frontend/src' -Recurse -Filter '*.jsx' -File -ErrorAction SilentlyContinue ^| Sort-Object FullName; if(-not $files){ 'nohash'; exit 0 }; $joined=($files ^| ForEach-Object { $h=(Get-FileHash -Algorithm SHA256 -Path $_.FullName).Hash.ToLower(); $_.FullName + '|' + $h }) -join \"`n\"; $bytes=[Text.Encoding]::UTF8.GetBytes($joined); $sha=[Security.Cryptography.SHA256]::Create(); (($sha.ComputeHash($bytes) ^| ForEach-Object { $_.ToString('x2') }) -join '')"') do set "JSX_HASH=%%H"
    set "JSX_HASH_FILE=frontend\node_modules\.jsx_hash"
    set "RUN_JSX_VALIDATE=0"
    if not exist "!JSX_HASH_FILE!" set "RUN_JSX_VALIDATE=1"
    if exist "!JSX_HASH_FILE!" (
        set /p STORED_JSX_HASH=<"!JSX_HASH_FILE!"
        if /I not "!STORED_JSX_HASH!"=="!JSX_HASH!" set "RUN_JSX_VALIDATE=1"
    )

    if "!RUN_JSX_VALIDATE!"=="1" (
        if exist "frontend\validate.cjs" (
            echo [INFO] Validando JSX con Babel...
            node frontend\validate.cjs
            if errorlevel 1 (
                echo [ERROR] Errores en JSX detectados. Corrige los archivos marcados.
                exit /b 1
            )
            >"!JSX_HASH_FILE!" echo !JSX_HASH!
            echo [INFO] JSX validado correctamente
        ) else (
            echo [WARN] frontend\validate.cjs no encontrado - omitiendo validacion JSX
        )
    ) else (
        echo [INFO] JSX sin cambios, omitiendo validacion Babel
    )
)

:: Arrancar frontend
echo [INFO] Arrancando frontend en puerto %FRONTEND_PORT%...
set "FRONTEND_RUNNER=%TEMP%\contecflow-frontend-runner.cmd"
(
    echo @echo off
    echo cd /d "%SCRIPT_DIR%\frontend"
    echo npm run dev -- --port %FRONTEND_PORT% 1^>"%TEMP%\contecflow-frontend.log" 2^>"%TEMP%\contecflow-frontend.err.log"
) > "%FRONTEND_RUNNER%"
start "Contecflow Frontend" /min "%COMSPEC%" /c call "%FRONTEND_RUNNER%"
if errorlevel 1 (
    echo [ERROR] No se pudo lanzar el frontend.
    exit /b 1
)

:: Esperar frontend (máx. 180 s)
echo [INFO] Esperando frontend
set FRONTEND_ATTEMPTS=0
:wait_frontend
set /a FRONTEND_ATTEMPTS+=1
if %FRONTEND_ATTEMPTS% GTR 180 (
    echo [ERROR] El frontend no respondio en 180 segundos.
    echo [ERROR] Revisa los logs: %TEMP%\contecflow-frontend.log y %TEMP%\contecflow-frontend.err.log
    exit /b 1
)
curl --silent --fail --connect-timeout 1 --max-time 1 "http://localhost:%FRONTEND_PORT%" >nul 2>&1
if NOT "%ERRORLEVEL%"=="0" (
    timeout /t 1 /nobreak >nul
    goto :wait_frontend
)
echo [INFO] Frontend listo

echo.
echo ============================================
echo   Contecflow listo [OK]
echo ============================================
echo.
echo   App:      http://localhost:%FRONTEND_PORT%
echo   API:      http://localhost:%BACKEND_PORT%/api/v1/docs
echo   Logs:     %TEMP%\contecflow-backend.log
echo.
call :get_demo_password
echo   Usuarios de prueba:
echo     admin      / !DEMO_PASSWORD!   - Direccion
echo     ana.torres / !DEMO_PASSWORD!   - PM
echo     luis.vega  / !DEMO_PASSWORD!   - Empleado
echo     rrhh       / !DEMO_PASSWORD!   - RRHH
echo.
echo   Para parar:  setup.bat stop
echo.

timeout /t 2 /nobreak >nul
start "" "http://localhost:%FRONTEND_PORT%"

echo Presiona cualquier tecla para cerrar esta ventana...
echo ^(Los servicios continuan en segundo plano^)
pause >nul
goto :end

:: -----------------------------------------------------------------------
:stop_services
echo [INFO] Parando Contecflow...
taskkill /FI "WINDOWTITLE eq Contecflow Backend*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Contecflow Frontend*" /F >nul 2>&1
call :kill_port %BACKEND_PORT%
call :kill_port %FRONTEND_PORT%
call :wait_port_free %BACKEND_PORT% 15 >nul 2>&1
call :wait_port_free %FRONTEND_PORT% 15 >nul 2>&1
echo [OK] Servicios parados.
goto :end

:: -----------------------------------------------------------------------
:kill_port
setlocal EnableDelayedExpansion
set "TARGET_PORT=%~1"
if "%TARGET_PORT%"=="" (
    endlocal & exit /b 0
)

for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr ":%TARGET_PORT% " ^| findstr "LISTENING"') do (
    taskkill /F /T /PID %%P >nul 2>&1
)

endlocal & exit /b 0

:: -----------------------------------------------------------------------
:wait_port_free
setlocal EnableDelayedExpansion
set "TARGET_PORT=%~1"
set "MAX_WAIT=%~2"
if not defined MAX_WAIT set "MAX_WAIT=15"
set /a WAIT_COUNT=0

:wait_port_free_loop
set /a WAIT_COUNT+=1
set "PORT_STATE=FREE"
for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr ":%TARGET_PORT% " ^| findstr "LISTENING"') do (
    set "PORT_STATE=BUSY"
)
if /I "!PORT_STATE!"=="FREE" (
    endlocal & exit /b 0
)
if !WAIT_COUNT! GEQ %MAX_WAIT% (
    endlocal & exit /b 1
)
timeout /t 1 /nobreak >nul
goto :wait_port_free_loop

:: -----------------------------------------------------------------------
:get_demo_password
:: Sin fallback: inventar una contraseña por defecto aquí significaba que un .env
:: sin DEFAULT_USER_PASSWORD acababa con usuarios cuya contraseña estaba escrita
:: en este script. Si queda vacía, quien llama debe abortar.
set "DEMO_PASSWORD="
for /f "tokens=1,* delims==" %%A in ('findstr /b "DEFAULT_USER_PASSWORD=" .env 2^>nul') do set "DEMO_PASSWORD=%%B"
exit /b 0

:: -----------------------------------------------------------------------
:: Entorno declarado en .env. Fail-closed: si no se puede determinar, se asume
:: "production" para que ninguna operación destructiva se ejecute por descuido.
:get_environment
set "APP_ENVIRONMENT="
for /f "tokens=1,* delims==" %%A in ('findstr /b "ENVIRONMENT=" .env 2^>nul') do set "APP_ENVIRONMENT=%%B"
if "!APP_ENVIRONMENT!"=="" set "APP_ENVIRONMENT=production"
exit /b 0

:: -----------------------------------------------------------------------
:sync_demo_passwords
setlocal EnableDelayedExpansion

:: Gate de entorno (auditoría 2026-08, P0-4). Esta rutina reescribe el hash de
:: contraseña de admin/ana.torres/luis.vega/rrhh con DEFAULT_USER_PASSWORD. Sin
:: guarda, ejecutar setup.bat contra producción dejaba la cuenta admin con una
:: contraseña conocida y compartida.
call :get_environment
set "ENV_OK="
if /i "!APP_ENVIRONMENT!"=="development" set "ENV_OK=1"
if /i "!APP_ENVIRONMENT!"=="dev"         set "ENV_OK=1"
if /i "!APP_ENVIRONMENT!"=="local"       set "ENV_OK=1"
if /i "!APP_ENVIRONMENT!"=="test"        set "ENV_OK=1"
if /i "!APP_ENVIRONMENT!"=="testing"     set "ENV_OK=1"
if /i "!APP_ENVIRONMENT!"=="demo"        set "ENV_OK=1"
if not defined ENV_OK (
    echo [WARN] ENVIRONMENT=!APP_ENVIRONMENT!: se OMITE la sincronizacion de contrasenas demo.
    echo [WARN] Reescribir credenciales solo se permite en development/test/demo.
    endlocal
    exit /b 0
)

call :get_demo_password
set "DEMO_PWD=!DEMO_PASSWORD!"
if "!DEMO_PWD!"=="" (
    echo [WARN] DEFAULT_USER_PASSWORD no esta definida en .env: se omite la sincronizacion.
    endlocal
    exit /b 0
)

:: Centinela de cambio. Antes se escribía la contraseña EN CLARO en este fichero
:: (se llamaba .pwd_hash pero no lo era): ahora se guarda su SHA-256.
set "PWD_HASH_FILE=.venv\.pwd_hash"
set "CURRENT_HASH="
for /f "delims=" %%H in ('.venv\Scripts\python -c "import hashlib,os;print(hashlib.sha256(os.environ['DEMO_PWD'].encode()).hexdigest())"') do set "CURRENT_HASH=%%H"
if "!CURRENT_HASH!"=="" set "CURRENT_HASH=nocheck"

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
