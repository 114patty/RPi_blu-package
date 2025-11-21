# raspberryMongoDB
respberry與MongoDB串接程式

## Raspberry Pi 4 model B+ UART收值環境設定

打開樹莓派配置
```bash
~$ sudo raspi-config
```
Expand filesystem --- advanced --- serial (enable)
```bash
~$ sudo reboot
```
查看當前 serial 映射關係
```bash
~$ ls -l /dev
```
官方默認為

`serial0 -> ttyS0`

`serial1 -> ttyAMA0`

#### Raspberry Pi 4 bluetooth 與 uart 衝突，系統默認 bluetooth，故關閉藍芽
```bash
~$ sudo nano /boot/config.txt
```
於 config.txt 文件最後添加(不能有空格)
```bash
dtoverlay=disable-bt
```
```bash
dtoverlay=miniuart-bt
```
重啟
```bash
~$ sudo reboot
```
再次查看當前 serial 映射關係
```bash
~$ ls -l /dev
```
可看到改變為

`serial0 -> ttyAMA0`

`serial1 -> ttyS0`

參考資料:
* https://blog.csdn.net/xinluosiding/article/details/109786923
* https://dumbcatnote.blogspot.com/2020/04/raspberry-pi-enable-serial-port.html

## Raspberry Pi 4 model B+ 設定自動啟動

### 1. 在 /home/pi 內新增一個 autostart.sh檔案
可使用以下命令建立並編輯檔案：
```bash
~$ sudo nano autostart.sh
```
在檔案中新增以下程式碼：
```bash
#!/bin/bash
sleep 4                  [等待樹莓派環境執行(若不加可能會因為網路尚未連線導致程式中斷)]
cd /home/{pi}/Desktop/   [此為要執行檔案的路徑，{pi}可改為你的名稱]
python start.py          [此為要執行的檔案]

```
編輯完成，按 `Ctrl+x` 離開，再按 `Y` 儲存，按下 `Enter` 及儲存完畢。

### 2. 給予 autostart.sh 檔案執行權限
```bash
~$ sudo chmod +x /home/{pi}/autostart.sh
```
### 3. 進入系統中新增要自動執行的程式
```bash
~$ sudo nano /etc/xdg/lxsession/LXDE-pi/autostart
```
在檔案最後一行加上：
```bash
@lxterminal -e bash /home/{pi}/autostart.sh
```
### 4. 完成，重新啟動測試看看
```bash
~$ sudo reboot
```
參考資料:
* https://yayar.medium.com/%E6%A8%B9%E8%8E%93%E6%B4%BE-%E9%96%8B%E6%A9%9F%E8%87%AA%E5%8B%95%E9%96%8B%E5%95%9Fterminal%E5%9F%B7%E8%A1%8Cpython%E7%A8%8B%E5%BC%8F-87b6a1690f0a
* https://forums.raspberrypi.com/viewtopic.php?t=294014