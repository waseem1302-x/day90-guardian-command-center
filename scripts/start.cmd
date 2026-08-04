@echo off
setlocal

cd /d "%~dp0\.."

echo.
echo ========================================
echo   Day90 Guardian Command Center
echo ========================================
echo.
echo Starting Docker services with rebuild...

docker compose up --build -d
if errorlevel 1 (
  echo.
  echo ERROR: Docker Compose failed.
  echo Make sure Docker Desktop is running, then run this file again.
  exit /b 1
)

echo.
echo Waiting for frontend at http://127.0.0.1:3001 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ready=$false; for($i=1; $i -le 30; $i++){ try { $r=Invoke-WebRequest -Uri 'http://127.0.0.1:3001' -UseBasicParsing -TimeoutSec 3; if($r.StatusCode -eq 200){ $ready=$true; break } } catch {}; Start-Sleep -Seconds 2 }; if($ready){ Write-Host 'Ready: http://127.0.0.1:3001' -ForegroundColor Green; exit 0 } else { Write-Host 'Frontend not ready yet. Run: docker compose logs frontend --tail=80' -ForegroundColor Yellow; exit 1 }"

endlocal
