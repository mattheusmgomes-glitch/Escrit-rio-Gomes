@echo off
REM Gera dist\EscritorioGomes\EscritorioGomes.exe (pode ser copiado para outros computadores).
cd /d "%~dp0"
if not exist .venv ( py -3 -m venv .venv )
call .venv\Scripts\activate.bat
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --windowed --name EscritorioGomes --collect-all google.ads.googleads --collect-data grpc escritorio_gomes\__main__.py
echo.
echo Executavel gerado em dist\EscritorioGomes\EscritorioGomes.exe
pause
