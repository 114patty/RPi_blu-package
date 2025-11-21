import socket 
from PyQt5 import  QtCore
import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish
from retry import retry
import threading
import time

class MQTTMOD(QtCore.QThread):

    control = QtCore.pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent) 
        self.client = None
        self.connected = False
        print("MQTT模組初始化")
    def run(self):
    
        """"""
        while not self.connected:
            try:

                self.client = mqtt.Client()
                self.client.username_pw_set(username="utl_food",password="utl2041")
                self.client.on_connect = self.on_connect
                self.client.on_disconnect = self.on_disconnect
                self.client.on_message = self.on_message
                #self.client.connect("114.34.73.26", 1883, 60)
                # self.client.connect("114.32.77.107", 1883, 60)
                self.client.connect("218.161.3.98", 1883, 60)
                
                
                self.client.loop_start()
                print("📡 正在連接 MQTT broker...")
                break
      
            except Exception as e:
                print(f"❌ MQTT 連線失敗：{e}")
                time.sleep(5)  # 每 5 秒重試

    @retry(tries=3, delay=1)
    def on_connect(self,client, userdata, flags, rc):
        # print("Connected with result code "+str(rc))
        if rc == 0:
            print("connect mqtt broker success")
            self.connected = True
            self.client.subscribe("Food/Camera")

        else:
            print(f"⚠️ MQTT broker 連線失敗，RC: {rc}")
            self.connected = False
            # 將訂閱主題寫在on_connet中
            # 如果我們失去連線或重新連線時
            # 地端程式將會重新訂閱

    def on_disconnect(self, client, userdata, rc):
        # ✅ [6] ➤ 當斷線時自動背景重連
        print("⚠️ MQTT broker 斷線，嘗試重連...")
        self.connected = False
        self.reconnect_thread = threading.Thread(target=self.reconnect)
        self.reconnect_thread.start()

    def reconnect(self):
        while not self.connected:
            try:
                if self.client is not None:
                    self.client.reconnect()
                    self.connected = True
                    print("🔄 MQTT 重連成功")
                else:
                    print("⚠️ client 尚未初始化，延遲重連")
                time.sleep(5)
            except Exception as e:
                print(f"❌ 重連失敗: {e}")
                time.sleep(5)

# 當接收到從伺服器發送的訊息時要進行的動作
    def on_message(self,client, userdata, msg):
        # 轉換編碼utf-8才看得懂中文
        print(msg.topic+" "+ msg.payload.decode('utf-8'))
        if msg.payload.decode('utf-8') == 'shot':
            self.control.emit('shot')
        elif msg.payload.decode('utf-8') == 'stop':
            self.control.emit('stop') 
    def send_message(self,MacAddress,message):
        if not self.connected:
            print("⚠️ 無法送出 MQTT 訊息，尚未連線")
            return
        try:
            publish.single(
                topic=f"Food/Camera",#Food/F05ECD2ABE8D/Camera
                payload= message,
                hostname="218.161.3.98",
                port=1883,
                auth={'username':'utl_food','password':'utl2041'})

            self.client.publish("Food/Camera", payload=message)
            print(f'mqtt send message successful, Message: {message}')

        except Exception as e:
            print('mqtt send message error!!')
    def killThread(self):
        self.wait()
        self.client.disconnect()
if __name__=="__main__":
    mq = MQTTMOD()
    mq.run()
    mq.send_message()

