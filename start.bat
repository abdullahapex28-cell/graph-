@echo off
REM ============================================================
REM  Learning Path Engine - start backend + frontend
REM  Always uses the project virtual environment (backend\test).
REM ============================================================

echo.
echo  Starting Learning Path Engine...
echo.

REM --- Preflight ---------------------------------------------------------
if not exist "backend\test\Scripts\python.exe" (
    echo  [X] Virtual environment not found at backend\test
    echo.
    echo      Run this once:
    echo          cd backend
    echo          python -m venv test
    echo          test\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo  [1/4] Checking environment...
cd backend
test\Scripts\python.exe -m scripts.preflight
cd ..

REM --- Neo4j check --------------------------------------------------------
echo.
echo  [2/4] Seeding the 100-node Physics graph...
cd backend
test\Scripts\python.exe -m scripts.seed_physics --reset
cd ..

REM --- Backend ------------------------------------------------------------
echo.
echo  [3/4] Starting backend on http://localhost:8000 ...
start "Learning Path - Backend" cmd /k "cd backend && test\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

REM --- Frontend -----------------------------------------------------------
echo  [4/4] Starting frontend on http://localhost:3000 ...
start "Learning Path - Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo  ============================================================
echo   Backend   http://localhost:8000
echo   API Docs  http://localhost:8000/docs
echo   Frontend  http://localhost:3000
echo  ============================================================
echo.
echo  IMPORTANT: the backend must be started with the venv interpreter
echo             (backend\test\Scripts\python.exe), not plain `python`.
echo             Plain `python` will not have networkx/pulp installed.
echo.
pause
