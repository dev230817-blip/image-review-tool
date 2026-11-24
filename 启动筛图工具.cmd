@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "REVIEW_PY="
if defined IMAGE_REVIEW_PYTHON call :probe "%IMAGE_REVIEW_PYTHON%"
if defined REVIEW_PY goto run_path
call :probe "%ProgramData%\miniconda3\python.exe"
if defined REVIEW_PY goto run_path
call :probe "%ProgramData%\anaconda3\python.exe"
if defined REVIEW_PY goto run_path
call :probe "%USERPROFILE%\miniconda3\python.exe"
if defined REVIEW_PY goto run_path
call :probe "%USERPROFILE%\anaconda3\python.exe"
if defined REVIEW_PY goto run_path
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 -c "import sys; sys.exit(sys.version_info < (3, 7))" >nul 2>nul
if not errorlevel 1 goto run_py
:try_python
where python >nul 2>nul
if errorlevel 1 goto missing
python -c "import sys; sys.exit(sys.version_info < (3, 7))" >nul 2>nul
if not errorlevel 1 goto run_python
:missing
echo 未检测到可用的 Python。可以直接双击“筛选工具.html”使用。
echo 如需自动保存本地 CSV，请安装 Python，或设置 IMAGE_REVIEW_PYTHON。
pause
exit /b 1
:run_path
"%REVIEW_PY%" -B -X utf8 "%~dp0筛选工具.py" %*
set "REVIEW_EXIT=%errorlevel%"
goto finished
:run_py
py -3 -B -X utf8 "%~dp0筛选工具.py" %*
set "REVIEW_EXIT=%errorlevel%"
goto finished
:run_python
python -B -X utf8 "%~dp0筛选工具.py" %*
set "REVIEW_EXIT=%errorlevel%"
:finished
pause
exit /b %REVIEW_EXIT%
:probe
if not exist "%~1" exit /b
"%~1" -c "import sys; sys.exit(sys.version_info < (3, 7))" >nul 2>nul
if not errorlevel 1 set "REVIEW_PY=%~1"
exit /b
