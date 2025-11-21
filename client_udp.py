#main code

#add date(Y_M_D_H_M_S), save to .txt
import serial # type: ignore
import queue
import time
from datetime import datetime, timedelta, timezone
import socket
from mqttMod import MQTTMOD
from mqtt_status import MQTTStatus
from pymongo import MongoClient # type: ignoreteghh
import uuid
import re
import subprocess 
import threading


device_id = hex(uuid.getnode())[2:].upper()


ser = serial.Serial('/dev/ttyAMA0', 115200)    #Open port with baud rate
uart_read_queue = queue.Queue(maxsize=50)
uart_write_queue = queue.Queue()
HOST = '218.161.3.98' #serverIP 
PORT = 8001 #server port
server_addr = (HOST, PORT)
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# --- MongoDB 連線設定 ---
# 例如：MONGO_URI = "mongodb://192.168.1.100:27017/"
# MONGO_URI = "mongodb://192.168.1.194:27017/"   #food  
# MONGO_URI = "mongodb://192.168.1.104:27017/"  #utl-net
MONGO_URI = "mongodb://utl:2041$$@218.161.3.98:27017/"  #server


DB_NAME = f"{device_id}"  # 你想儲存數據的資料庫名稱
# DB_NAME = "F332"  # 你想儲存數據的資料庫名稱
COLLECTION_NAME = "posture_data" # 你想儲存數據的集合名稱

def network_connected():
    try:
        # 嘗試連接 Google 網站的 80 port
        socket.create_connection(("google.com", 80), timeout=3)
        return True
    except Exception:
        return False
    
def wait_for_network():
    while not network_connected():
        print("🌐 等待網路連線中...")
        time.sleep(5)

# 在一開始執行
wait_for_network()

def utc_z(dt: datetime) -> str:
    """aware UTC datetime -> 'YYYY-MM-DDTHH:MM:SSZ'"""
    return dt.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')

def decode_data(data):
    clear_data = data[:]
    utc_now = datetime.now(timezone.utc)
    #now = datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=8)))
    # packet = clear_data + datetime.now(timezone.utc).isoformat().replace("+00:00", "Z") + 'r9'
    packet = clear_data + str(datetime.utcnow() + timedelta(hours = 8)) + 'r9' 
    # print("[decode_data] UTC time in packet:", utc_z(utc_now))
    return packet

# 手環封包 16byte -> 10byte
def packet_value(packet,index,n = 49):
    data_only = packet[1:1 + n *2]
    values = [data_only[i:i+2] for i in range(0, len(data_only),2)]
    if index < len(values):
        return int(values[index],16)
    else:
        return None
# 手環封包(4 bits) 16byte -> 10byte
def four_byte_value(packet,index,n = 49):
    data_only = packet[1:1 + n *2]
    values = [data_only[i:i+2] for i in range(0, len(data_only),2)]
    if index +1 < len(values):
        combine = values[index + 1] + values[index]
        return int(combine,16)
    else:
        return None,None

def valid_mac(mac):
    """檢查 MAC 格式是否合法（過濾假裝置）"""
    if not mac or not isinstance(mac, str):
        return False
    mac = mac.strip().upper()

    # 格式必須是 12 位十六進制
    if not re.fullmatch(r"[0-9A-F]{12}", mac):
        return False

    # 排除全 0、全 F 或開頭兩個以上的 0
    if mac in ("000000000000", "FFFFFFFFFFFF"):
        return False
    # ❌ 含有連續三個以上的 0
    if re.search(r"0{3,}", mac):
        return False
     # ❌ 開頭或尾巴是 "00" 或 "000"
    if mac.startswith(("00", "000")) or mac.endswith(("00", "000")):
        return False

    # 可以再排除一些明顯不合理的樣式（例如太多重複）
    if mac.count(mac[0]) > 5:
        return False

    return True

def valid_device(data):
    """檢查裝置資料是否完整有效"""
    required_fields = [
        "safe_Mac", "ACC_X", "ACC_Y", "ACC_Z",
        "roll16", "pitch16", "yaw16", "HR", "Step"
    ]
    for field in required_fields:
        if field not in data or data[field] is None:
            return False
    # 再檢查 MAC 合法性
    if not valid_mac(data["safe_Mac"]):
        return False
    return True

class Uart_Read: 
    def __init__(self, read_queue, write_queue, ser):
        self.read_queue = read_queue
        self.write_queue = write_queue
        self.ser = ser
        self.if_upload = False
        self.state = 0 #用來鎖定相機觸發
        self.mqtt = MQTTMOD()
        self.mqtt.start()

        self.area1_count = 0
        self.area2_count = 0

        # --- MongoDB 連線初始化 ---
        self.mongo_collection = None
        self.connect_to_mongodb() # 在初始化時嘗試連接 MongoDB
        self.known_macs = set()  # 記錄當次執行期間所有出現過的 MAC
        self.failed_queue = queue.Queue(maxsize=10000)  # 暫存失敗上傳的資料
        threading.Thread(target=self.retry_failed_uploads, daemon=True).start()


    def connect_to_mongodb(self):
        """嘗試連接到 MongoDB 資料庫並設定 self.mongo_collection，若失敗則每 5 秒重試"""
        while True:
            # ✅（新增）先檢查網路狀態
            if not network_connected():
                print("🌐 網路未連線，5 秒後再試...")
                time.sleep(5)
                continue

            try:
                print("正在嘗試連接 MongoDB...")
                client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000) # 設定連線逾時
                client.admin.command('ping') # 嘗試執行一個簡單的操作來確認連線是否成功
                db = client[DB_NAME]
                self.mongo_collection = db[COLLECTION_NAME]
                self.mongo_collection_device = db["mac_devices"]

                # ✅ 確保 mac 欄位唯一（防止重複插入）
                self.mongo_collection_device.create_index("mac", unique=True)

                # 初始化合法 MAC 清單
                valid_macs = []
                cutoff_time = datetime.now(timezone.utc) - timedelta(days=7)


                for d in self.mongo_collection_device.find():
                    mac = d.get("mac", "")
                    if not valid_mac(mac):
                        # 格式錯誤 → 刪除
                        self.mongo_collection_device.delete_one({"_id": d["_id"]})
                        print(f"已刪除無效 MAC：{mac}")
                        continue

                    # 檢查 posture_data 是否有一天內的資料
                    last_data = self.mongo_collection.find_one(
                        {"safe_Mac": mac, "timestamp": {"$gte": cutoff_time}},
                        sort=[("timestamp", -1)]
                    )

                    if last_data:
                        valid_macs.append(mac)
                    else:
                        # 一天內沒資料 → 刪掉
                        self.mongo_collection_device.delete_one({"_id": d["_id"]})
                        print(f"已刪除超過一天無資料的 MAC：{mac}")

                self.mac_list = valid_macs
                self.known_macs = set(valid_macs)  # ✅ 從資料庫載入到本地集合

                print("合法裝置 MAC 清單：", self.mac_list)
                print(f"🔄 已載入 {len(self.known_macs)} 個已知 MAC")
                print("成功連接到 MongoDB！")

                # ✅補上傳失敗資料 queue
                if hasattr(self, "failed_queue") and self.failed_queue.qsize() > 0:
                    print("🔁 補上傳之前失敗的資料...")
                    while not self.failed_queue.empty():
                        item = self.failed_queue.get()
                        try:
                            self.mongo_collection.insert_one(item)
                            print("   → 已補傳成功")
                        except Exception as e:
                            print("❌ 補上傳失敗，重新放回 queue")
                            self.failed_queue.put(item)
                            break  # 避免 MongoDB 又中斷，造成死循環

                break
            except Exception as e:
                print(f"連接 MongoDB 失敗: {e}")
                print("5 秒後重試連線...")
                time.sleep(5)
                print("請檢查以下事項：")
                print(f"  1. 確保電腦 {MONGO_URI} 的 IP 地址正確。")
                print("  2. 確保電腦上的 MongoDB 服務正在運行。")
                print("  3. 確保電腦的防火牆允許樹莓派連線到 MongoDB 端口 (預設 27017)。")
                print("  4. 確保 MongoDB 配置檔 (mongod.conf) 中的 bindIp 設定為 0.0.0.0 或你的電腦 IP。")
                self.mongo_collection = None # 連線失敗則設為 None
                self.mongo_collection_device = None
                self.mac_list = []
                self.known_macs = set()


    def run(self):
        while True:
            try:
                data = self.ser.readline().decode()
                if (uart_write_queue.qsize() > 0):
                    uart_write_data = uart_write_queue.get()
                    ser.write(uart_write_data.decode('hex'))
            
                packet = decode_data(data)
                if not packet or len(packet) < 200:
                    print("⚠️ 跳過異常封包")
                    continue

                print("="*10+"start")
                print(packet)

                # print(len(packet))

                power = packet_value(packet,42)
                blood_oxygen = packet_value(packet,34)
                heart_rate = packet_value(packet,43)
                calories = four_byte_value(packet,40)
                step = four_byte_value(packet,36)
                Press_16 = (self.twosComplement_hex(packet[165:169]) / 100.0) + 900
                Point = int(packet[185:187],16) #Beacon定位點
                Area = int(packet[187:189],16) #靠近幾號Beacon



                if len(packet) == 233:  # 辨識封包是否為手環封包
                    json_pakage = self.decode_json(packet)
                    safe_mac = json_pakage["safe_Mac"]

                    # TARGET_MAC = "E8DC28011294"
                    # if safe_mac != TARGET_MAC:
                    #         continue  # 直接跳過，這筆資料不處理

                    # ✅ 檢查 MAC + 必要資料是否完整
                    if valid_device(json_pakage):
                        # === 新增防重複 MAC 清單 ===
                        if not hasattr(self, "known_macs"):
                            self.known_macs = set()

                        # --- 自動偵測新裝置並新增 ---
                        # if safe_mac not in self.known_macs:
                        #     # 先檢查 MongoDB 裡是否已存在
                        #     exists = False
                        #     if self.mongo_collection_device:
                        #         exists = self.mongo_collection_device.count_documents({"mac": safe_mac}, limit=1) > 0

                        #     if not exists:
                        #         print(f"✅ 偵測到新裝置 MAC：{safe_mac}（首次新增）")
                        #         try:
                        #             self.mongo_collection_device.insert_one({"mac": safe_mac})
                        #         except Exception as insert_e:
                        #             print(f"⚠️ 新增 MAC 到 mac_devices 失敗: {insert_e}")

                        #     # 不論資料庫是否已有，都更新本地清單
                        #     self.known_macs.add(safe_mac)
                        #     if safe_mac not in self.mac_list:
                        #         self.mac_list.append(safe_mac)
                        # 檢查這個 MAC 是否是新的（不在 mac_list 裡）
                        if safe_mac not in self.mac_list:
                            print(f"📡 偵測到新裝置：{safe_mac}")
                            try:
                                self.mongo_collection_device.insert_one({"mac": safe_mac})
                                self.mac_list.append(safe_mac)
                                self.known_macs.add(safe_mac)
                                print(f"✅ 已新增新裝置 MAC：{safe_mac}")
                            except Exception as e:
                                if "E11000" in str(e):
                                    # 已存在（重複）→ 忽略
                                    print(f"⚠️ 跳過重複 MAC：{safe_mac}")
                                else:
                                    print(f"❌ 新增 MAC 時發生錯誤：{e}")

                        else:
                            # 已在記錄中，不重複加入或顯示
                            pass

                        # --- 將數據上傳到 MongoDB ---
                        if self.mongo_collection:
                            try:
                                json_pakage["device_ID"] = device_id
                                self.mongo_collection.insert_one(json_pakage)
                                # print(f"數據已上傳到 MongoDB: {safe_mac}")
                            except Exception as mongo_e:
                                print(f"插入數據到 MongoDB 失敗: {mongo_e}. 嘗試重新連線...")
                                print("MongoDB 寫入失敗，暫存資料待補上傳")
                                self.failed_queue.put(json_pakage)  # 存進 queue
                                self.connect_to_mongodb()
                                if self.mongo_collection:
                                    try:
                                        self.mongo_collection.insert_one(json_pakage)
                                    except Exception as retry_mongo_e:
                                        print(f"重新連線後再次插入失敗: {retry_mongo_e}")
                                else:
                                    print("無法重新連線到 MongoDB，數據可能丟失。")
                        else:
                            print("MongoDB 未連線，數據未上傳。")

                        # UDP 傳送
                        s.sendto(packet.encode(), server_addr)

                    else:
                        print(f"⛔ 忽略無效或不完整裝置資料，MAC={safe_mac}")

                    # --- MongoDB 上傳結束 ---

                    s.sendto(packet.encode(), server_addr)
                    if self.if_upload == True :
                        """"""
                    area_position = json_pakage["Area"]
                    posture = json_pakage["Posture_state"]
                    safe_mac = json_pakage["safe_Mac"]
                    # tmp = json_pakage["Ambient temperature"]
                    press = json_pakage["Press_16"]
                    rssi = json_pakage['RSSI']
                    acc_x = json_pakage['ACC_X']
                    acc_y = json_pakage['ACC_Y']
                    acc_z = json_pakage['ACC_Z']
                    roll = json_pakage["roll16"]
                    pitch = json_pakage["pitch16"]
                    yaw = json_pakage["yaw16"]
                    mag_x = json_pakage['MAG_X']
                    mag_y = json_pakage['MAG_Y']
                    mag_z = json_pakage['MAG_Z']

                    # Mac1 = "FCA89B57D8BE" #Mac of old_safe_device for TI
                    # Mac2 = "D34F0197CB78" #Mac of safe_device for Nordic
                    Mac3 = "EAC5BC8732A7" #Mac of newest_safe_device for Nordic
                    Mac4 = "C06EAC5BF9B0" #

                    if safe_mac in self.mac_list:                   # or sorted(safe_mac) == sorted(Mac3):
                        print("="*10)
                        print(f"device_ID:{device_id}"+"\n"
                              +f"safe_Mac:{safe_mac}"+"\n"
                              +f"ACC_X:{acc_x}"+"\n" #f"ACC_X:{acc_x}"+"="*5 #Original format
                              +f"ACC_Y:{acc_y}"+"\n"
                              +f"ACC_Z:{acc_z}"+"\n"
                              +f"roll:{roll}"+"\n"
                              +f"pitch:{pitch}"+"\n"
                              +f"yaw:{yaw}"+"\n"
                              +f"MAG_X:{mag_x}"+"\n"
                              +f"MAG_Y:{mag_y}"+"\n"
                              +f"MAG_Z:{mag_z}"+"\n"
                              +f"Press_16:{Press_16:.2f}"+"\n"
                              +f"Posture:{posture}"+"\n"
                              +f"Point:{Point}"+"\n"
                              +f"Area:{Area}")
                        print("="*5+"手環數據"+"="*5)
                        print(f"Power:{power}"+"\n"
                              f"Blood Oxygen:{blood_oxygen}"+"\n"
                              f"Heart Rate:{heart_rate}"+"\n"
                              f"Calories:{calories}"+"\n"
                              f"Steps:{step}"+"\n")
                        print("="*10+"end")
                        # print(f"Area:{area_position}"+"="*5+f"Mac:{safe_mac}"+"="*5+f"Posture:{posture}")
                        # print(f"Posture:{posture}"+"="*5+f"Area:{area_position}"+"="*5+f"Mac:{safe_mac}"+"="*5+f"tmp:{tmp}")

                        if area_position == 1:
                            self.area1_count += 1
                            print(f"area1_count:{self.area1_count}")
                            if posture == 1 and self.state == 0 and self.area1_count >= 3:
                                self.mqtt.send_message(safe_mac,"shot") 
                                self.state = 1 # 將狀態切換至用餐
                                print("用餐")
                                self.area2_count = 0
                                print(f"area2_1_count:{self.area2_count}")

                        elif area_position != 1:
                            self.area2_count += 1    
                            print(f"area2_count:{self.area2_count}")
                            if posture == 2 and self.state == 1 and self.area2_count >= 3:
                                if sorted(safe_mac) == sorted(Mac3) and sorted(Mac4):
                                    self.mqtt.send_message(safe_mac,"stop") 
                                    self.state = 0 #將狀態切換至結束
                                    print("結束")
                                    self.area1_count = 0
                                    print(f"area1_1_count:{self.area1_count}")

                    time.sleep(.03)
            except Exception as e:
                print(e)

    def retry_failed_uploads(self):
        """背景執行：只要 MongoDB 恢復就自動補上傳"""
        while True:
            try:
                if self.mongo_collection is not None and self.failed_queue.qsize() > 0:
                    print("🔄 嘗試補上傳 queue 中的資料...")

                    temp_list = []  # 暫存一次要上傳多少筆（避免 Queue 阻塞）

                    while not self.failed_queue.empty():
                        temp_list.append(self.failed_queue.get())

                    for item in temp_list:
                        try:
                            self.mongo_collection.insert_one(item)
                            print("   → 補傳成功")
                        except Exception as e:
                            print(f"❌ 補傳失敗：{e}, 放回 queue")
                            self.failed_queue.put(item)
                            break  # 避免連續錯誤

                # 若 MongoDB 斷線 → 嘗試重連
                if self.mongo_collection is None:
                    self.connect_to_mongodb()

            except Exception as e:
                print(f"背景補傳錯誤：{e}")

            time.sleep(3)   # 每 3 秒檢查一次
            
     # 緊急封包判斷
    def judgeState(self,raw_data):
        if raw_data[0:3] == '$0C': #一般封包$0C
            safe_sos = 0
            return safe_sos
        elif raw_data[0:3] == '$4C': #緊急封包$4C
            safe_sos = 1
            return safe_sos
        
    # 將十六進制的值轉為有正負號的十進制值
    def twosComplement_hex(self,hexval):
        bits = 16 # Number of bits in a hexadecimal number format
        val = int(hexval, 16)
        if val & (1 << (bits-1)):
            val -= 1 << bits
        return val


    def tmpIdentify(self,raw_data, state):
        if state == 1:
            tmp = str(int(raw_data[71:73],16))+str(int(raw_data[73:75],16))
            return tmp
        elif state == 2:
            tmp = str(int(raw_data[71:75],16))
            return tmp
        elif state == 3:
            tmp = str(int(raw_data[71:75],16))
            return tmp
        else:
            return "tmpIdentify error"
    def decode_json(self,indata):
        """"""
        raw_data = indata
        now = datetime.now()
        utc_now = datetime.now(timezone.utc)
        time = utc_now.isoformat(timespec='milliseconds')
        # current_time_iso = datetime.now()

        band_Mac = raw_data[5:17]
        state = int(raw_data[97:99],16) # 1為舊手環, 2為新手環, 3為蓋德
        tmp = self.tmpIdentify(raw_data, state)
        sleep = int(raw_data[87:89],16)*60 + int(raw_data[89:91],16)
        blood_oxygen = packet_value(raw_data,34)
        calories = four_byte_value(raw_data,40)
        step = four_byte_value(raw_data,36)
        heart_rate = packet_value(raw_data,43)
        mileage = str(packet_value(raw_data,38)) + "." + str(packet_value(raw_data,39))

        if len(raw_data) != 233:
            print(f"⚠️ 封包長度錯誤 ({len(raw_data)} bytes)，跳過。")
            return None
        safe_Mac = raw_data[189:201]

        raw_data_document = {
            # 協定換算方式:ex 血壓35~36 => 35*2-1=69 => 所以血壓的位置位於raw_data的第69個，有4個bytes，69~72為血壓的判讀區域，剩下的以此類推。
            'timestamp': utc_now,
            'state' : self.judgeState(raw_data), #確認封包狀態
            'raspberry_Mac' : raw_data[-2:],
            'safe_Mac' : safe_Mac,
            'safe_battery': int(raw_data[201:203],16),    #低頭功能203-205
            'Posture_state' : int(raw_data[173:175],16),
            'band_Mac' : raw_data[5:17],
            #-----------------事與物(暫時沒用到)--------------
            # 'Sensor' : int(raw_data[33:34],16),
            # 'MybeBehavior' : int(raw_data[34:35],16),
            # 'Room' : int(raw_data[35:36],16),
            # 'Furniture' : int(raw_data[36:37],16),
            # 'Behavior' : int(raw_data[37:38],16),
            # 'BehaviorQulity' : int(raw_data[38:39],16),
            # 'Alertvalue' : int(raw_data[39:51],16),
            #-----------------手環生理訊號--------------------
            'HR' : heart_rate,                                              #int(raw_data[51:53],16),
            # 'Bloodpressure_SBP' : int((raw_data[53:55]),16),
            # 'Bloodpressure_DBP' : int((raw_data[55:57]),16),
            'Step' : step,                                                  #int((raw_data[57:59] + raw_data[59:61]),16),
            'Mileage' : mileage,                                                    #int((raw_data[61:63] + raw_data[63:65]),16)/1000,
            'Blood_oxygen' : blood_oxygen,                                  #int((raw_data[65:67]),16),
            'Calories' : calories,                                          #int((raw_data[67:69] + raw_data[69:71]),16),
            'band_battery' : int(raw_data[85:87],16),
            # 'Temperature' : tmp[0:2] + '.' + tmp[2:4], # 體溫
            # 'Sleep' : sleep, # 單位:min
            # 'Nap' : int(raw_data[91:93],16),
            # 'SOS' : int(raw_data[93:95],16),
            # 'Button' : int(raw_data[95:97],16),
            # 'New&Old' : state,
            #----------------手環生化訊號(暫時沒用到)----------
            # 'Takemedicine1' : int(raw_data[113:115],16),
            # 'Takemedicine2' : int(raw_data[115:117],16),
            # 'Bloodsugar' : int(raw_data[117:119],16),
            # 'Lacticacid' : int(raw_data[119:121],16),
            #-----------------護身符--------------------------
            'ACC_X' : self.twosComplement_hex(raw_data[121:125])/512,
            'ACC_Y' : self.twosComplement_hex(raw_data[125:129])/512,
            'ACC_Z' : self.twosComplement_hex(raw_data[129:133])/512,
            'ACC_total' : self.twosComplement_hex(raw_data[133:137])/512,
            'roll16' : self.twosComplement_hex(raw_data[137:141])/100,
            'pitch16' : self.twosComplement_hex(raw_data[141:145])/100,
            'yaw16' : self.twosComplement_hex(raw_data[145:149])/100,
            'MAG_X' : self.twosComplement_hex(raw_data[149:153]),
            'MAG_Y' : self.twosComplement_hex(raw_data[153:157]),
            'MAG_Z' : self.twosComplement_hex(raw_data[157:161]),
            'MAG_total' : self.twosComplement_hex(raw_data[161:165]),
            'Press_16' : (self.twosComplement_hex(raw_data[165:169]) / 100.0) + 900, # (+80000)/100
            # 'Ambient temperature' : self.twosComplement_hex(raw_data[169:173])*0.0625, #環境溫度
            # 'Azimuth16' : self.twosComplement_hex(raw_data[175:179]),
            'Direction' : int(raw_data[179:181],16), #方位
            'RSSI' : self.twosComplement_hex(raw_data[181:185]), #護身符與Beacon的距離
            'Point' : int(raw_data[185:187],16), #Beacon定位點
            'Area' : int(raw_data[187:189],16) #靠近幾號Beacon
        }
        return raw_data_document
    
# --- 你的 MQTT Broker 資訊 ---
BROKER_HOST = "218.161.3.98"
BROKER_PORT = 1883
USERNAME = None  # 若有帳密就填
PASSWORD = None

status = MQTTStatus(
    host=BROKER_HOST, port=BROKER_PORT,
    username=USERNAME, password=PASSWORD,
    keepalive=30, hb_sec=60
)
while not network_connected():
    print("🌐 等待網路恢復再啟動 MQTTStatus...")
    time.sleep(5)

status.start()   # ⬅ 開始上線宣告與心跳

dd = Uart_Read(uart_read_queue, uart_write_queue, ser)
print("UART 讀取服務啟動中...")
try:
    dd.run()
except KeyboardInterrupt:
    print("程式手動終止。")
except Exception as e:
    print(f"主程式錯誤: {e}")
finally:
    if ser.is_open:
        ser.close()
        print("UART 端口已關閉。")
    # if hasattr(dd, 'mqtt') and dd.mqtt: # 如果有 MQTT 實例，記得停止
    #     dd.mqtt.stop()
    if dd.mongo_collection and dd.mongo_collection.database.client:
        dd.mongo_collection.database.client.close()
        print("MongoDB 連線已關閉。")
    status.stop()