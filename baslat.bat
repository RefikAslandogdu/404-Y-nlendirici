@echo off
chcp 65001 >nul
echo 404 Yonlendirici baslatiliyor...
echo.
echo Gerekli paketler yukleniyor...
pip install flask openpyxl rapidfuzz >nul 2>&1
echo Paketler hazir.
echo.
echo Tarayici aciliyor...
start http://localhost:5050
echo.
echo Sunucu calisiyor. Bu pencereyi kapatmayin.
echo Kapatmak icin CTRL+C basin.
echo.
python app.py
pause
