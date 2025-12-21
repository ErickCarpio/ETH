@echo off
echo ========================================
echo ACTUALIZACION DEL BOT - TESTNET FIX
echo ========================================
echo.

echo 1. Guardando tus cambios locales...
git stash push -m "Config local antes de actualizar"

echo.
echo 2. Descargando ultimos cambios del repo...
git pull origin claude/review-code-errors-LsmkW

echo.
echo 3. Restaurando tus cambios locales...
git stash pop

echo.
echo ========================================
echo ACTUALIZACION COMPLETADA
echo ========================================
echo.
echo IMPORTANTE:
echo 1. Si hay conflictos en config_15min.json, abrelo y resuelve manualmente
echo 2. Busca las lineas con "<<<<<<" y ">>>>>>" y elige la version correcta
echo 3. Asegurate de mantener tus API keys de testnet si las tenias
echo.
echo Presiona cualquier tecla para continuar...
pause
