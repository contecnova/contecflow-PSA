@echo off
setlocal EnableDelayedExpansion

:: Contecflow - Script de instalación para Windows
:: Uso (sin argumentos muestra esta lista):
::   setup.bat demo^|clean - instala y arranca con modo de datos
::   setup.bat install  - instala y pregunta el modo de datos
::   setup.bat start    - solo arranca
::   setup.bat start demo^|clean - solo arranca con modo de datos
::   setup.bat stop     - para los servicios
::   setup.bat update   - actualiza dependencias y esquema (migraciones)
::   setup.bat docker [demo^|clean] - TODO en Docker (app + Grafana/Prometheus/Alertmanager)
::   setup.bat docker-status - estado de los contenedores y URLs
::   setup.bat docker-stop / docker-clean - para Docker (clean borra los volumenes regenerables; conserva PostgreSQL y S3)
::   setup.bat backup   - copia local (SQLite o PostgreSQL + uploads) en backups\
::   setup.bat restore ^<carpeta^> - restaura una copia (verifica integridad antes)
::   setup.bat test-postgres / cobertura / lint-css - calidad a mano (ver README)
::   SETUP_INIT_MODE=demo^|clean setup.bat start  - modo no interactivo (CI/CD)
::   BACKEND_PORT / FRONTEND_PORT / CF_REDIS_PORT - puertos (8000 / 3000 / 6381)
::   CONTECFLOW_TAREAS=auto^|celery^|integrado - como corren las tareas programadas

:: La consola de Windows arranca en la pagina de codigos 850 o 1252, y el
:: sembrado imprime «checks» y avisos con caracteres fuera de ASCII: 81 `print`
:: en 14 ficheros. Sin esto, `setup.bat demo` moria con UnicodeEncodeError a
:: mitad del sembrado y dejaba la base CON CERO USUARIOS — instalacion
:: aparentemente hecha y sin forma de entrar.
::
:: `PYTHONUTF8=1` es el modo UTF-8 de Python 3.7+: afecta a todo lo que lanza
:: este script, no solo al sembrado. Se fija aqui y no con `chcp` para no
:: cambiarle la consola al usuario.
set PYTHONUTF8=1

:: Puertos: los del entorno si vienen (set BACKEND_PORT=8010 y luego setup.bat
:: start); si no, los de siempre. Igual que setup.sh. Hasta el 23-11-2026
:: estaban fijos y un "set BACKEND_PORT=..." previo se pisaba aqui.
if not defined BACKEND_PORT set "BACKEND_PORT=8000"
if not defined FRONTEND_PORT set "FRONTEND_PORT=3000"
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

:: Sin argumentos se muestra la ayuda (igual que setup.sh). Antes, `setup.bat`
:: a secas lanzaba la instalacion completa con pregunta interactiva, y cualquier
:: opcion desconocida (p. ej. `setup.bat Demo2`) hacia lo mismo en silencio.
set "CMD=%~1"
if "%CMD%"=="" goto :usage

if /I "%CMD%"=="help"   goto :usage
if /I "%CMD%"=="-h"     goto :usage
if /I "%CMD%"=="--help" goto :usage
if /I "%CMD%"=="/?"     goto :usage

if /I "%CMD%"=="start"        goto :start_only
if /I "%CMD%"=="stop"         goto :stop_services
if /I "%CMD%"=="update"       goto :update_mode
if /I "%CMD%"=="docker-stop"  goto :docker_stop
if /I "%CMD%"=="docker-clean" goto :docker_clean
if /I "%CMD%"=="docker"        goto :docker_full
if /I "%CMD%"=="docker-start"  goto :docker_full
if /I "%CMD%"=="docker-up"     goto :docker_full
if /I "%CMD%"=="docker-status" goto :docker_status
if /I "%CMD%"=="backup"        goto :backup_local
if /I "%CMD%"=="restore"       goto :restore_local
if /I "%CMD%"=="test-postgres" goto :calidad
if /I "%CMD%"=="cobertura"     goto :calidad
if /I "%CMD%"=="lint-css"      goto :lint_css

if /I "%CMD%"=="install" set "REQUESTED_MODE="& goto :full_install
if /I "%CMD%"=="demo"  set "REQUESTED_MODE=demo"
if /I "%CMD%"=="seed"  set "REQUESTED_MODE=demo"
if /I "%CMD%"=="clean" set "REQUESTED_MODE=clean"
if /I "%CMD%"=="zero"  set "REQUESTED_MODE=clean"
if /I "%CMD%"=="cero"  set "REQUESTED_MODE=clean"
if /I "%CMD%"=="admin-only" set "REQUESTED_MODE=clean"
if /I "%CMD%"=="admin_only" set "REQUESTED_MODE=clean"

if not "%REQUESTED_MODE%"=="" goto :full_install

echo [ERROR] Opcion desconocida: %CMD%
echo.
goto :usage

:usage
echo Uso:
echo   setup.bat demo               -^> instala y arranca con datos demo
echo   setup.bat clean              -^> instala y arranca con BD vacia ^(solo admin^)
echo   setup.bat install            -^> instala y pregunta el modo de datos
echo   setup.bat start              -^> solo arranca ^(BD existente^)
echo   setup.bat start demo^|clean   -^> arranca re-sembrando con ese modo
echo   setup.bat stop               -^> para la app ^(Docker sigue activo^)
echo   setup.bat update             -^> actualiza dependencias y esquema (migraciones)
echo   setup.bat docker [demo^|clean] -^> TODO en Docker: app, API, worker, beat, web,
echo                                   Prometheus, Alertmanager, Grafana y exporters
echo   setup.bat docker-status      -^> estado de los contenedores y URLs
echo   setup.bat docker-stop        -^> para todos los contenedores ^(conserva datos^)
echo   setup.bat docker-clean       -^> para Docker y borra los volumenes regenerables ^(conserva PostgreSQL y S3^)
echo   setup.bat backup             -^> copia local: base ^(SQLite o PostgreSQL^) + uploads en backups
echo   setup.bat restore ^<carpeta^>  -^> verifica la copia, para la app y la restaura ^(pide confirmacion^)
echo   setup.bat test-postgres [args de pytest] -^> tests contra un PostgreSQL efimero en Docker
echo   setup.bat cobertura [--solo backend^|frontend] [args de pytest] -^> informes en la carpeta cobertura
echo   setup.bat lint-css           -^> stylelint sobre frontend\src
echo.
echo   Alias: seed = demo; zero / cero / admin-only = clean
echo   CI/CD: set SETUP_INIT_MODE=demo^|clean ^&^& setup.bat start
echo   Puertos: set BACKEND_PORT=8010, FRONTEND_PORT=3010 o CF_REDIS_PORT=6381 antes de setup.bat
echo   Tareas:  set CONTECFLOW_TAREAS=auto^|celery^|integrado ^(auto: Celery si hay Redis; si no, integrado^)
endlocal
exit /b 1

:: Calidad a mano (24-11-2026): nunca en hooks ni CI y sin umbrales. La logica
:: vive en scripts\test_postgres.py y scripts\cobertura.py (las mismas que
:: setup.sh y make). Lo que va detras del comando se pasa tal cual (a pytest,
:: o --solo backend^|frontend a la cobertura). Ver README, "Calidad a mano".
:: `shift` no cambia %*, por eso se recogen uno a uno.
:calidad
if not exist "%SCRIPT_DIR%\.venv\Scripts\python.exe" (
    echo [ERROR] Falta el entorno virtual. Ejecuta antes: setup.bat install
    endlocal
    exit /b 1
)
set "CALIDAD_ARGS="
:calidad_args
shift
if "%~1"=="" goto :calidad_run
set CALIDAD_ARGS=!CALIDAD_ARGS! %1
goto :calidad_args
:calidad_run
cd /d "%SCRIPT_DIR%"
set "CALIDAD_SCRIPT=scripts\cobertura.py"
if /I "%CMD%"=="test-postgres" set "CALIDAD_SCRIPT=scripts\test_postgres.py"
.venv\Scripts\python !CALIDAD_SCRIPT! !CALIDAD_ARGS!
set "CALIDAD_RC=!errorlevel!"
endlocal & exit /b %CALIDAD_RC%

:lint_css
cd /d "%SCRIPT_DIR%\frontend"
call npm run lint:css
set "CALIDAD_RC=!errorlevel!"
endlocal & exit /b %CALIDAD_RC%

:: Copias locales (23-11-2026). scripts\backup.sh y restore.sh solo cubrian
:: Docker; la logica comun (SQLite con la API de backup, PostgreSQL con
:: pg_dump, uploads y verificacion SHA-256) vive en scripts\copia_local.py,
:: que tambien usa setup.sh. Ver README, "Copias de seguridad".
:backup_local
if not exist "%SCRIPT_DIR%\.venv\Scripts\python.exe" (
    echo [ERROR] Falta el entorno virtual. Ejecuta antes: setup.bat install
    endlocal
    exit /b 1
)
cd /d "%SCRIPT_DIR%"
.venv\Scripts\python scripts\copia_local.py backup
if errorlevel 1 (
    echo [ERROR] La copia de seguridad ha fallado. Revisa el mensaje de arriba.
    endlocal
    exit /b 1
)
goto :end

:restore_local
if "%~2"=="" (
    echo [ERROR] Uso: setup.bat restore ^<carpeta de la copia en backups, o su MANIFIESTO^>
    endlocal
    exit /b 1
)
if not exist "%SCRIPT_DIR%\.venv\Scripts\python.exe" (
    echo [ERROR] Falta el entorno virtual. Ejecuta antes: setup.bat install
    endlocal
    exit /b 1
)
cd /d "%SCRIPT_DIR%"
:: Primero se comprueba la copia sin tocar nada; solo si es integra se para la
:: app (con la base abierta Windows no deja reemplazar el fichero SQLite).
.venv\Scripts\python scripts\copia_local.py verificar "%~2"
if errorlevel 1 (
    echo [ERROR] La copia no supera la verificacion de integridad: no se restaura nada.
    endlocal
    exit /b 1
)
echo [INFO] Parando la app antes de restaurar...
call :parar_procesos
.venv\Scripts\python scripts\copia_local.py restore "%~2"
if errorlevel 1 (
    echo [ERROR] La restauracion no se ha completado. Revisa el mensaje de arriba.
    endlocal
    exit /b 1
)
echo [OK] Restaurado. Arranca con: setup.bat start
goto :end

:docker_stop
:: Todos los perfiles (infra, app, observabilidad, s3, host-metrics), sin -v:
:: los datos se conservan. Igual que `./setup.sh docker-stop`.
echo [INFO] Parando todos los contenedores de Contecflow...
call :docker_compose --profile app --profile observability --profile s3 --profile host-metrics down
if errorlevel 1 goto :end
echo [OK] Docker detenido (datos conservados en volumenes)
goto :end

:: Modo Docker completo (22-11-2026, docs\OBSERVABILIDAD.md). La logica vive en
:: scripts\docker_stack.py, compartida con setup.sh: los dos lanzadores hacen lo
:: mismo (volumenes persistentes creados y nunca borrados, .env completado,
:: build + up de infra, app y observabilidad, migraciones, espera y URLs).
:docker_full
call :docker_stack_python
if errorlevel 1 goto :error
"!DS_PY!" "%SCRIPT_DIR%\scripts\docker_stack.py" arrancar %2
if errorlevel 1 goto :error
goto :end

:docker_status
call :docker_stack_python
if errorlevel 1 goto :error
"!DS_PY!" "%SCRIPT_DIR%\scripts\docker_stack.py" estado
goto :end

:: Python para scripts\docker_stack.py: el de .venv si existe; si no, el del
:: sistema (solo usa la biblioteca estandar).
:docker_stack_python
set "DS_PY="
if exist "%SCRIPT_DIR%\.venv\Scripts\python.exe" set "DS_PY=%SCRIPT_DIR%\.venv\Scripts\python.exe"
if defined DS_PY exit /b 0
for %%p in (py python3 python) do (
    if not defined DS_PY (
        where %%p >nul 2>&1
        if not errorlevel 1 (
            for /f "delims=" %%x in ('%%p -c "import sys; print(sys.executable)" 2^>nul') do if not defined DS_PY set "DS_PY=%%x"
        )
    )
)
if defined DS_PY exit /b 0
echo [ERROR] Hace falta Python 3 para el modo Docker ^(https://www.python.org/downloads/^)
exit /b 1

:docker_clean
call :get_environment
set "ENV_OK="
for %%E in (development dev local test testing demo) do (
    if /I "!APP_ENVIRONMENT!"=="%%E" set "ENV_OK=1"
)
if not defined ENV_OK (
    echo [ERROR] docker-clean borra los volumenes y ENVIRONMENT=!APP_ENVIRONMENT!. Solo en desarrollo o pruebas.
    endlocal
    exit /b 2
)
REM Auditoria 22-11-2026 (01 B3): todos los perfiles y mensaje veraz: PostgreSQL y S3
REM son volumenes externos, protegidos de "down -v" a proposito, y se conservan.
echo [INFO] Parando Docker ^(todos los perfiles^) y borrando los volumenes regenerables...
call :docker_compose --profile app --profile s3 --profile observability --profile host-metrics down -v --remove-orphans
if errorlevel 1 goto :end
echo [OK] Docker detenido; borrados Redis, Prometheus, Alertmanager y Grafana.
echo [AVISO] Se CONSERVAN los datos de PostgreSQL y S3 ^(contecflow_postgres_data y contecflow_s3_data^).
echo [AVISO] Para borrarlos de verdad: docker volume rm contecflow_postgres_data contecflow_s3_data
goto :end

:: Ejecuta `docker compose` (o `docker-compose` antiguo) en la carpeta del proyecto.
:docker_compose
if not exist "%SCRIPT_DIR%\docker-compose.yml" (
    echo [WARN] docker-compose.yml no encontrado
    exit /b 1
)
where docker >nul 2>&1
if errorlevel 1 (
    echo [WARN] Docker no disponible
    exit /b 1
)
pushd "%SCRIPT_DIR%"
docker compose version >nul 2>&1
if errorlevel 1 (
    docker-compose %*
) else (
    docker compose %*
)
set "DC_RC=!errorlevel!"
popd
exit /b %DC_RC%

:full_install
call :setup_backend
if errorlevel 1 goto :error
call :setup_frontend
if errorlevel 1 goto :error
call :apply_migrations
if errorlevel 1 goto :error
call :resolve_init_mode "%REQUESTED_MODE%"
if errorlevel 1 goto :error
call :apply_selected_data_mode
if errorlevel 1 goto :error
call :start_services
goto :end

:start_only
echo [INFO] Modo: solo arrancar
set "REQUESTED_MODE=%~2"
if not exist "%SCRIPT_DIR%\.venv\Scripts\python.exe" (
    call :setup_backend
    if errorlevel 1 goto :error
)
if not exist "%SCRIPT_DIR%\frontend\node_modules\vite\dist\node\cli.js" (
    call :setup_frontend
    if errorlevel 1 goto :error
)
call :apply_migrations
if errorlevel 1 goto :error
:: Como `setup.sh start`: sin modo explicito (argumento o SETUP_INIT_MODE) se
:: conserva la BD. Antes preguntaba demo/clean en cada arranque y re-sembraba
:: o vaciaba la base aunque solo se quisiera arrancar.
if "%REQUESTED_MODE%%SETUP_INIT_MODE%"=="" (
    echo [INFO] Se conserva la base de datos existente
    goto :start_only_run
)
call :resolve_init_mode "%REQUESTED_MODE%"
if errorlevel 1 goto :error
call :apply_selected_data_mode
if errorlevel 1 goto :error
:start_only_run
call :start_services
goto :end

:update_mode
echo [INFO] Modo: actualizar dependencias y esquema
call :setup_backend
if errorlevel 1 goto :error
call :setup_frontend
if errorlevel 1 goto :error
call :prepare_app_role
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
:apply_migrations
echo.
echo [INFO] Aplicando migraciones con Alembic...
cd /d "%SCRIPT_DIR%"
:: Alembic es la UNICA fuente de verdad del esquema, igual que en setup.sh y en
:: docker-compose. Este paso FALTABA aqui: `setup.bat` no tenia una sola
:: aparicion de alembic, asi que tras un `git pull` la base se quedaba con el
:: esquema viejo y el sembrado moria con «no such column» a mitad — dejando la
:: instalacion aparentemente hecha y la base sin usuarios.
::
:: `upgrade head` es idempotente y barato cuando no hay revisiones pendientes,
:: asi que se ejecuta siempre y no se intenta adivinar si hace falta.
.venv\Scripts\python scripts\migrar.py
if errorlevel 1 (
    echo [ERROR] Las migraciones han fallado.
    echo [ERROR] NO se arranca con un esquema a medias: revisa el error de arriba.
    echo [ERROR] Si la base local esta corrupta, borrala y vuelve a ejecutar
    echo [ERROR] este script: Alembic la reconstruye entera desde cero.
    exit /b 1
)
:: alembic_version puede decir head sin haber ejecutado las revisiones (stamp a
:: mano, base copiada de otra maquina): se comprueba el esquema real.
.venv\Scripts\python scripts\comprobar_esquema.py
if errorlevel 1 exit /b 1
echo [OK] Esquema al dia
call :prepare_app_role
exit /b 0

:: -----------------------------------------------------------------------
:prepare_app_role
:: Auditoria 22-11-2026 (A1): igual que setup.sh. Con Postgres, la aplicacion
:: conecta con un rol sin superusuario ni BYPASSRLS (APP_DB_USER, contrasena
:: generada en .env) y las migraciones con el dueno (DATABASE_MIGRATIONS_URL).
:: Con SQLite no hace nada. CONTECFLOW_DB_APP_ROLE=0 lo omite.
cd /d "%SCRIPT_DIR%"
set "APP_ROLE_OUT="
for /f "delims=" %%R in ('.venv\Scripts\python scripts\rol_de_aplicacion.py') do set "APP_ROLE_OUT=%%R"
if not defined APP_ROLE_OUT exit /b 0
if /I "!APP_ROLE_OUT:~0,3!"=="OK " (
    echo [OK] RLS: !APP_ROLE_OUT:~3!
) else if /I "!APP_ROLE_OUT:~0,5!"=="SKIP " (
    echo [INFO] RLS: omitido ^(!APP_ROLE_OUT:~5!^)
) else (
    echo [WARN] RLS: no se pudo preparar el rol de aplicacion ^(!APP_ROLE_OUT:~5!^); la aplicacion sigue con el dueno
)
exit /b 0

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
        echo [ERROR] No se pudo descargar Python. Instalalo manualmente desde https://python.org
        exit /b 1
    )
    "!PY_INSTALLER!" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    if errorlevel 1 (
        echo [ERROR] No se pudo instalar Python automaticamente.
        echo [ERROR] Instalalo manualmente desde https://www.python.org/downloads/ y reinicia el terminal.
        del "!PY_INSTALLER!" >nul 2>&1
        exit /b 1
    )
    del "!PY_INSTALLER!" >nul 2>&1
    set PYTHON=python

    where !PYTHON! >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python se instalo, pero no esta en PATH en esta sesion.
        echo [ERROR] Cierra y abre el terminal, o instala manualmente desde https://www.python.org/downloads/
        exit /b 1
    )

    for /f "tokens=*" %%v in ('!PYTHON! -c "import sys; v=sys.version_info; print(v.major*100+v.minor)" 2^>nul') do set PY_VER_NUM=%%v
    if not defined PY_VER_NUM (
        echo [ERROR] No se pudo verificar la version de Python tras la instalacion.
        exit /b 1
    )
    if !PY_VER_NUM! LSS 310 (
        echo [ERROR] Python detectado no cumple version minima 3.10+.
        echo [ERROR] Instala manualmente una version compatible desde https://www.python.org/downloads/
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

:: Solo Windows: Python usa su propia lista de CAs (certifi), no la de Windows.
:: Detras de un proxy corporativo con inspeccion TLS, las llamadas HTTPS (p.ej.
:: proveedores de IA) fallaban con CERTIFICATE_VERIFY_FAILED. pip-system-certs
:: hace que Python confie en el almacen de certificados de Windows.
.venv\Scripts\python -m pip show pip-system-certs >nul 2>&1
if errorlevel 1 (
    echo [INFO] Instalando pip-system-certs ^(certificados de Windows para Python^)...
    .venv\Scripts\python -m pip install --quiet pip-system-certs || echo [WARN] No se pudo instalar pip-system-certs ^(no es bloqueante^)
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
        echo ALLOWED_ORIGINS=["http://localhost:%FRONTEND_PORT%","http://localhost:5173","http://localhost:%BACKEND_PORT%"]
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
    echo [WARN] CLIENT_PORTAL_SECRET no encontrado en .env - anadiendo valor por defecto
    >>.env echo CLIENT_PORTAL_SECRET=contecflow-portal-secret-change-in-production
)
findstr /b "SECRET_KEY=" .env >nul 2>&1
if errorlevel 1 (
    echo [WARN] SECRET_KEY no encontrado en .env - anadiendo valor por defecto
    >>.env echo SECRET_KEY=contecflow-secret-key-change-in-production-min32chars
)
findstr /b "SUPERADMIN_EMAIL=" .env >nul 2>&1
if errorlevel 1 (
    echo [WARN] SUPERADMIN_EMAIL no encontrado en .env - anadiendo valor por defecto
    >>.env echo SUPERADMIN_EMAIL=admin@company.com
)
findstr /b "SUPERADMIN_PASSWORD=" .env >nul 2>&1
if errorlevel 1 (
    echo [WARN] SUPERADMIN_PASSWORD no encontrado en .env - generando una aleatoria
    for /f "delims=" %%S in ('powershell -NoProfile -Command "[System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(15)).Replace('+','x').Replace('/','y').Replace('=','') + 'Aa1!'"') do >>.env echo SUPERADMIN_PASSWORD=%%S
)
findstr /b "DEFAULT_USER_PASSWORD=" .env >nul 2>&1
if errorlevel 1 (
    echo [WARN] DEFAULT_USER_PASSWORD no encontrado en .env - generando una aleatoria
    for /f "delims=" %%S in ('powershell -NoProfile -Command "[System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(15)).Replace('+','x').Replace('/','y').Replace('=','') + 'Aa1!'"') do >>.env echo DEFAULT_USER_PASSWORD=%%S
)
:: ENVIRONMENT gobierna el gate de :sync_demo_passwords. Si falta, los scripts
:: asumen production y NO reescriben credenciales.
findstr /b "ENVIRONMENT=" .env >nul 2>&1
if errorlevel 1 (
    echo [INFO] ENVIRONMENT no encontrado en .env - estableciendo development
    >>.env echo ENVIRONMENT=development
)
:: 23-11-2026: un valor que Settings acepte (canonico o alias, ver .env.example).
:: Antes un ENVIRONMENT desconocido pasaba el setup y la API no arrancaba.
call :get_environment
set "ENV_VALIDO="
for %%E in (development dev local demo test testing staging stage pre preprod production prod prd) do if /I "!APP_ENVIRONMENT!"=="%%E" set "ENV_VALIDO=1"
if not defined ENV_VALIDO (
    echo [ERROR] ENVIRONMENT=!APP_ENVIRONMENT! en .env no es valido: la API no arrancaria.
    echo [ERROR] Usa development, test, staging o production ^(alias: dev, local, demo, testing, stage, pre, preprod, prod, prd^).
    exit /b 1
)

:: Regenerar SECRET_KEY si quedó con placeholder/insegura
set "SECRET_STATUS="
for /f "delims=" %%S in ('.venv\Scripts\python scripts\rotar_secret_key.py') do set "SECRET_STATUS=%%S"
if /I "!SECRET_STATUS!"=="ROTATED" (
    echo [WARN] SECRET_KEY insegura detectada en .env - regenerada automaticamente
)

:: Esquema. BD con usuarios: `alembic upgrade head` (conserva los datos).
:: BD nueva, vacia o ilegible: se crea desde los modelos y se marca con
:: `alembic stamp head`. La cadena completa de revisiones no arranca sobre una
:: SQLite vacia (la 089 pide modelos ya retirados), y sin usuarios no hay nada
:: que conservar. El sembrado lo hace el modo demo/clean, no este paso.
:: El fichero sale de DATABASE_URL en .env (no siempre es contecflow.db). Si no
:: es SQLite, nunca se borra nada: se trata como base existente.
set "DB_URL="
set "DB_FILE="
for /f "tokens=1,* delims==" %%A in ('findstr /b "DATABASE_URL=" .env 2^>nul') do set "DB_URL=%%B"
if not defined DB_URL set "DB_URL=sqlite:///./contecflow.db"
if /I "!DB_URL:~0,10!"=="sqlite:///" (
    set "DB_FILE=!DB_URL:~10!"
    set "DB_FILE=!DB_FILE:/=\!"
)
set "DB_STATUS="
if not defined DB_FILE set "DB_STATUS=ok"
if defined DB_FILE if exist "!DB_FILE!" (
    for /f "tokens=*" %%r in ('.venv\Scripts\python -c "from app.db.session import SessionLocal, declarar_sistema; from app.models.user import User; db=declarar_sistema(SessionLocal(), 'setup: comprobar usuarios'); c=db.query(User).filter(User.hashed_password.isnot(None)).count(); db.close(); print('ok' if c>0 else 'empty')" 2^>nul') do set DB_STATUS=%%r
)

if "!DB_STATUS!"=="ok" (
    echo [INFO] Base de datos OK - datos existentes conservados
    .venv\Scripts\python scripts\migrar.py
    if errorlevel 1 (
        echo [ERROR] Fallo al aplicar migraciones.
        echo [ERROR] Revisa tu archivo .env ^(especialmente SECRET_KEY^) y vuelve a ejecutar setup.bat
        exit /b 1
    )
    .venv\Scripts\python scripts\comprobar_esquema.py
    if errorlevel 1 exit /b 1
) else (
    echo [INFO] Base de datos nueva o sin usuarios - creando esquema desde los modelos...
    del /f "!DB_FILE!" "!DB_FILE!-wal" "!DB_FILE!-shm" "!DB_FILE!-journal" >nul 2>&1
    if exist "!DB_FILE!" (
        echo [ERROR] No se pudo borrar !DB_FILE! ^(esta abierta en otro programa?^)
        exit /b 1
    )
    .venv\Scripts\python -c "import app.models; from app.db.base import Base; from app.db.session import engine; Base.metadata.create_all(bind=engine)"
    if errorlevel 1 (
        echo [ERROR] Fallo al crear el esquema de la base de datos.
        exit /b 1
    )
    .venv\Scripts\python -m alembic stamp head
    if errorlevel 1 (
        echo [ERROR] Fallo al marcar la version de Alembic.
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
        echo [ERROR] No se pudo descargar Node.js. Instalalo desde https://nodejs.org
        exit /b 1
    )
    msiexec /i "!NODE_INSTALLER!" /quiet /norestart
    if errorlevel 1 (
        echo [ERROR] No se pudo instalar Node.js automaticamente.
        echo [ERROR] Instalalo manualmente desde https://nodejs.org/ y reinicia el terminal.
        del "!NODE_INSTALLER!" >nul 2>&1
        exit /b 1
    )
    del "!NODE_INSTALLER!" >nul 2>&1
    where node >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Node.js se instalo, pero no esta en PATH en esta sesion.
        echo [ERROR] Cierra y abre el terminal, o instala manualmente desde https://nodejs.org/
        exit /b 1
    )
    where npm >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] npm no esta disponible tras la instalacion de Node.js.
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
    echo [WARN] Entorno virtual no encontrado. Inicializando backend automaticamente...
    call :setup_backend
    if errorlevel 1 exit /b 1
)

if not exist "%SCRIPT_DIR%\frontend\node_modules\vite\dist\node\cli.js" (
    echo [WARN] Frontend no preparado. Inicializando frontend automaticamente...
    call :setup_frontend
    if errorlevel 1 exit /b 1
)

:: Always sync demo passwords before starting -- ensures hash matches .env even on 'start only'
call :sync_demo_passwords

:: Tareas en segundo plano (23-11-2026). Antes se lanzaban SIEMPRE worker y beat
:: de Celery y la API sin planificador, pero este script no escribia REDIS_URL:
:: sin Redis los dos morian y no corria ninguna tarea programada. Ahora
:: scripts\modo_tareas.py busca un Redis que responda (REDIS_URL del .env, 6379
:: local o el de Docker en CF_REDIS_PORT) y escribe REDIS_URL si faltaba:
::   celery    = API con ENABLE_APSCHEDULER=0, mas worker y beat de Celery
::   integrado = API con el planificador integrado (APScheduler, que replica
::               todo el calendario de beat); no se lanzan procesos que fallarian
set "TAREAS_MODO="
set "TAREAS_DETALLE="
for /f "tokens=1,*" %%A in ('.venv\Scripts\python scripts\modo_tareas.py') do (
    set "TAREAS_MODO=%%A"
    set "TAREAS_DETALLE=%%B"
)
if /I "!TAREAS_MODO!"=="celery" goto :tareas_con_celery
set "TAREAS_MODO=integrado"
set "RUN_APSCHEDULER=1"
set "RUN_CELERY_BEAT=0"
echo.
echo [AVISO] ==========================================================
echo [AVISO] Sin Redis: !TAREAS_DETALLE!. Se arranca SIN Celery.
echo [AVISO] Las tareas programadas ^(SLA, buzon, avisos...^) las ejecuta el
echo [AVISO] planificador integrado de la API ^(APScheduler^). No se lanzan
echo [AVISO] worker ni beat. Lo que se encola al momento ^(.delay^) no corre.
echo [AVISO] Para usar Celery: arranca Redis ^(6379, o el de Docker en 6381^)
echo [AVISO] y vuelve a ejecutar setup.bat start.
echo [AVISO] ==========================================================
echo.
goto :tareas_decididas
:tareas_con_celery
set "RUN_APSCHEDULER=0"
set "RUN_CELERY_BEAT=1"
echo [OK] Tareas en segundo plano: Celery con Redis !TAREAS_DETALLE!
:tareas_decididas

:: Liberar puertos y procesos de un arranque anterior
taskkill /FI "WINDOWTITLE eq Contecflow Worker*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Contecflow Beat*" /F >nul 2>&1
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
REM Auditoria 22-11-2026 (01 B2): solo en este equipo (127.0.0.1); para abrirlo a la
REM red local, "set BACKEND_HOST=0.0.0.0" antes de setup.bat start. Docker no pasa por aqui.
if not defined BACKEND_HOST set "BACKEND_HOST=127.0.0.1"
(
    echo @echo off
    echo cd /d "%SCRIPT_DIR%"
    echo set ENABLE_APSCHEDULER=!RUN_APSCHEDULER!
    echo set ENABLE_CELERY_BEAT=!RUN_CELERY_BEAT!
    echo .venv\Scripts\python -m uvicorn app.main:app --host %BACKEND_HOST% --port %BACKEND_PORT% --log-level info 1^>"%TEMP%\contecflow-backend.log" 2^>"%TEMP%\contecflow-backend.err.log"
) > "%BACKEND_RUNNER%"
REM (call ) deja errorlevel a 0: si no, el "if errorlevel 1" de abajo hereda el de
REM cualquier orden anterior y da un falso "No se pudo lanzar" (22-11-2026).
(call )
start "Contecflow Backend" /min "%COMSPEC%" /c call "%BACKEND_RUNNER%"
if errorlevel 1 (
    echo [ERROR] No se pudo lanzar el backend.
    exit /b 1
)
REM Worker y beat solo con Redis (ver modo de tareas arriba). En Windows Celery
REM necesita el pool "solo".
if /I not "!TAREAS_MODO!"=="celery" goto :sin_worker_ni_beat
set "WORKER_RUNNER=%TEMP%\contecflow-worker-runner.cmd"
(
    echo @echo off
    echo cd /d "%SCRIPT_DIR%"
    echo .venv\Scripts\python -m celery -A app.worker.celery_app worker --loglevel=info --pool=solo 1^>"%TEMP%\contecflow-worker.log" 2^>^&1
) > "%WORKER_RUNNER%"
start "Contecflow Worker" /min "%COMSPEC%" /c call "%WORKER_RUNNER%"
set "BEAT_RUNNER=%TEMP%\contecflow-beat-runner.cmd"
(
    echo @echo off
    echo cd /d "%SCRIPT_DIR%"
    echo .venv\Scripts\python -m celery -A app.worker.celery_app beat --loglevel=info --schedule "%TEMP%\contecflow-celerybeat-schedule" 1^>"%TEMP%\contecflow-beat.log" 2^>^&1
) > "%BEAT_RUNNER%"
start "Contecflow Beat" /min "%COMSPEC%" /c call "%BEAT_RUNNER%"
:sin_worker_ni_beat

:: Esperar a que el backend responda (máx. 600 s backend / 300 s frontend: con la máquina cargada tarda varios minutos)
echo [INFO] Esperando backend
set BACKEND_ATTEMPTS=0
:wait_backend
set /a BACKEND_ATTEMPTS+=1
if %BACKEND_ATTEMPTS% GTR 600 (
    echo [ERROR] El backend no respondio en 600 segundos.
    echo [ERROR] Revisa los logs: %TEMP%\contecflow-backend.log y %TEMP%\contecflow-backend.err.log
    exit /b 1
)
curl --silent --fail --connect-timeout 1 --max-time 1 "http://127.0.0.1:%BACKEND_PORT%/health" >nul 2>&1
if NOT "%ERRORLEVEL%"=="0" (
    ping -n 2 127.0.0.1 >nul
    goto :wait_backend
)
echo [INFO] Backend listo

if not exist "frontend\node_modules" mkdir "frontend\node_modules" >nul 2>&1

set "VITE_HASH="
for /f "delims=" %%H in ('powershell -NoProfile -Command "$files=Get-ChildItem -Path 'frontend/src' -Recurse -File -Include '*.ts','*.tsx','*.js','*.jsx' -ErrorAction SilentlyContinue | Sort-Object FullName; if(-not $files){ 'nohash'; exit 0 }; $joined=($files | ForEach-Object { $h=(Get-FileHash -Algorithm SHA256 -Path $_.FullName).Hash.ToLower(); $_.FullName + '|' + $h }) -join [char]10; $bytes=[Text.Encoding]::UTF8.GetBytes($joined); $sha=[Security.Cryptography.SHA256]::Create(); (($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) -join '')"') do set "VITE_HASH=%%H"
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
    for /f "delims=" %%H in ('powershell -NoProfile -Command "$files=Get-ChildItem -Path 'frontend/src' -Recurse -Filter '*.jsx' -File -ErrorAction SilentlyContinue | Sort-Object FullName; if(-not $files){ 'nohash'; exit 0 }; $joined=($files | ForEach-Object { $h=(Get-FileHash -Algorithm SHA256 -Path $_.FullName).Hash.ToLower(); $_.FullName + '|' + $h }) -join [char]10; $bytes=[Text.Encoding]::UTF8.GetBytes($joined); $sha=[Security.Cryptography.SHA256]::Create(); (($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) -join '')"') do set "JSX_HASH=%%H"
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
    echo set API_URL=http://localhost:%BACKEND_PORT%
    echo npm run dev -- --port %FRONTEND_PORT% 1^>"%TEMP%\contecflow-frontend.log" 2^>"%TEMP%\contecflow-frontend.err.log"
) > "%FRONTEND_RUNNER%"
(call )
start "Contecflow Frontend" /min "%COMSPEC%" /c call "%FRONTEND_RUNNER%"
if errorlevel 1 (
    echo [ERROR] No se pudo lanzar el frontend.
    exit /b 1
)

:: Esperar frontend (máx. 600 s backend / 300 s frontend: con la máquina cargada tarda varios minutos)
echo [INFO] Esperando frontend
set FRONTEND_ATTEMPTS=0
:wait_frontend
set /a FRONTEND_ATTEMPTS+=1
if %FRONTEND_ATTEMPTS% GTR 300 (
    echo [ERROR] El frontend no respondio en 300 segundos.
    echo [ERROR] Revisa los logs: %TEMP%\contecflow-frontend.log y %TEMP%\contecflow-frontend.err.log
    exit /b 1
)
curl --silent --fail --connect-timeout 1 --max-time 1 "http://localhost:%FRONTEND_PORT%" >nul 2>&1
if NOT "%ERRORLEVEL%"=="0" (
    ping -n 2 127.0.0.1 >nul
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
if /I "!TAREAS_MODO!"=="celery" (
    echo   Tareas:   Celery ^(%TEMP%\contecflow-worker.log y contecflow-beat.log^)
) else (
    echo   Tareas:   planificador integrado de la API ^(sin Redis ni Celery^)
)
echo.
:: 23-11-2026: el banner decia DEFAULT_USER_PASSWORD tambien para admin, cuya
:: contrasena es SUPERADMIN_PASSWORD, y perdia los "!" por la expansion
:: retardada. Lo imprime Python directamente: cada usuario con la suya, solo
:: los que existen y sin contrasenas fuera de development/test.
.venv\Scripts\python scripts\credenciales_iniciales.py
echo.
echo   Para parar:  setup.bat stop
echo.

ping -n 3 127.0.0.1 >nul
start "" "http://localhost:%FRONTEND_PORT%"

echo Presiona cualquier tecla para cerrar esta ventana...
echo ^(Los servicios continuan en segundo plano^)
pause >nul
goto :end

:: -----------------------------------------------------------------------
:stop_services
echo [INFO] Parando Contecflow...
call :parar_procesos
echo [OK] Servicios parados.
goto :end

:parar_procesos
taskkill /FI "WINDOWTITLE eq Contecflow Backend*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Contecflow Frontend*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Contecflow Worker*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Contecflow Beat*" /F >nul 2>&1
call :kill_port %BACKEND_PORT%
call :kill_port %FRONTEND_PORT%
call :wait_port_free %BACKEND_PORT% 15 >nul 2>&1
call :wait_port_free %FRONTEND_PORT% 15 >nul 2>&1
exit /b 0

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
ping -n 2 127.0.0.1 >nul
goto :wait_port_free_loop

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
:: 23-11-2026: toda la logica en scripts\sincronizar_contrasenas_demo.py:
:: - puerta de entorno (auditoria 2026-08, P0-4): solo development/test y alias;
:: - admin (superadmin) con SUPERADMIN_PASSWORD y el resto con
::   DEFAULT_USER_PASSWORD, igual que la semilla (antes admin recibia aqui
::   DEFAULT_USER_PASSWORD y en la semilla SUPERADMIN_PASSWORD);
:: - las contrasenas se leen del .env en Python: por la consola, con la
::   expansion retardada, se perdian los "!";
:: - centinela con el SHA-256 de las dos (nunca en claro).
set "SYNC_OUT="
for /f "delims=" %%R in ('.venv\Scripts\python scripts\sincronizar_contrasenas_demo.py --centinela .venv\.pwd_hash 2^>nul') do set "SYNC_OUT=%%R"
if /I "!SYNC_OUT:~0,3!"=="ok:" (
    echo [INFO] Contrasenas demo alineadas con .env ^(!SYNC_OUT:~3! usuarios^)
) else if /I "!SYNC_OUT!"=="sin-cambios" (
    echo [INFO] Contrasenas demo sin cambios, omitiendo rehash
) else if /I "!SYNC_OUT:~0,8!"=="omitido:" (
    echo [WARN] Sincronizacion de contrasenas demo omitida: !SYNC_OUT:~8!
) else (
    echo [WARN] No se pudieron sincronizar las contrasenas demo: !SYNC_OUT!
)
endlocal
exit /b 0

:: -----------------------------------------------------------------------
:error
echo.
echo [ERROR] La instalacion ha fallado.
echo Comprueba los mensajes anteriores para ver el problema.
echo.
pause
exit /b 1

:end
endlocal
