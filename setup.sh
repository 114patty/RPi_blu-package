#!/bin/bash
echo "=== UTL IoT UDP Client 環境安裝腳本 ==="

# 更新系統
echo "[1/5] 更新套件清單..."
sudo apt-get update -y

# 安裝必要的系統套件
echo "[2/5] 安裝系統依賴..."
sudo apt-get install -y python3-venv python3-pip python3-pyqt5

# 建立虛擬環境 (允許使用系統套件，才能用到 apt 裝的 PyQt5)
echo "[3/5] 建立虛擬環境..."
rm -rf myenv
python3 -m venv myenv --system-site-packages

# 啟用虛擬環境
source myenv/bin/activate

# 安裝 Python 套件
echo "[4/5] 安裝 Python 套件..."
pip install --upgrade pip
pip install pyserial pymongo paho-mqtt retry

# 檢查 PyQt5
echo "[5/5] 測試 PyQt5..."
python3 -c "from PyQt5 import QtCore; print('PyQt5 OK, 版本:', QtCore.QT_VERSION_STR)"

# 檢查 UART
if [ -e /dev/ttyAMA0 ]; then
  echo "UART OK: /dev/ttyAMA0 存在"
else
  echo "⚠️ 找不到 UART /dev/ttyAMA0，請確認已在 /boot/config.txt 啟用 enable_uart=1"
fi

# 檢查 MongoDB 連線 (只測試 ping，不會插入資料)
echo "測試 MongoDB 連線..."
python3 - << 'EOF'
from pymongo import MongoClient
try:
    client = MongoClient("mongodb://218.161.3.98:27017/", serverSelectionTimeoutMS=3000)
    client.admin.command('ping')
    print("MongoDB 連線成功 ✅")
except Exception as e:
    print("MongoDB 連線失敗 ⚠️", e)
EOF

echo "=== 安裝完成，請執行 ==="
echo "source myenv/bin/activate && python3 client_udp.py"

