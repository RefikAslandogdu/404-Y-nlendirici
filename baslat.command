#!/bin/bash
cd "$(dirname "$0")"
echo "404 Yonlendirici baslatiliyor..."
echo ""
echo "Gerekli paketler yukleniyor..."
pip3 install flask openpyxl rapidfuzz > /dev/null 2>&1
echo "Paketler hazir."
echo ""
echo "Tarayici aciliyor..."
open http://localhost:5050 &
echo ""
echo "Sunucu calisiyor. Bu pencereyi kapatmayin."
echo "Kapatmak icin CTRL+C basin."
echo ""
python3 app.py
