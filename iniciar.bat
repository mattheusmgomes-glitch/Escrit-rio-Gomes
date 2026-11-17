@echo off
REM Instala (na primeira vez) e abre o Sistema Integrado do escritório.
cd /d "%~dp0"
if not exist .venv (
    echo Preparando o ambiente pela primeira vez...
    py -3 -m venv .venv || python -m venv .venv
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)
start "" pythonw -m escritorio_gomes
