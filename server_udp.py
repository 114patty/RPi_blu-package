import socket
from datetime import datetime,timezone,timedelta
from pymongo import MongoClient
from dateutil import parser

mogoClient = MongoClient('mongodb://localhost:27017/') # 可替換資料庫URL

HOST = '114.32.77.107'
# HOST = '114.34.73.26' # 此處IP要隨著server的網路位置做變更
PORT = 8001 # port值可不變更

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind((HOST, PORT))

print('server start at: {}{}'.format(HOST, PORT))
print('wait for connection...')

# 緊急封包判斷
def judgeState(raw_data):
    if raw_data[0:3] == '$0C': #一般封包$0C
        safe_sos = 0
        return safe_sos
    elif raw_data[0:3] == '$4C': #緊急封包$4C
        safe_sos = 1
        return safe_sos
    
# 將十六進制的值轉為有正負號的十進制值
def twosComplement_hex(hexval):
    bits = 16 # Number of bits in a hexadecimal number format
    val = int(hexval, bits)
    if val & (1 << (bits-1)):
        val -= 1 << bits
    return val


def tmpIdentify(raw_data, state):
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
        return "error"

dot = 0
while True:
    dt1 = datetime.utcnow().replace(tzinfo=timezone.utc)
    dt2 = dt1.astimezone(timezone(timedelta(hours=8))) # 轉換時區 -> 東八區
    timeString = dt2.strftime("%Y-%m-%dT%H:%M:%S")
    time = parser.parse(timeString)
    indata, addr = s.recvfrom(1024)
    # print('recvfrom ' + str(addr) + ': ' + indata.decode())
    
    # 決定存入資料庫的名稱(此用當日日期表示)
    date = datetime.now()
    dateString = date.strftime("%Y-%m-%d")
    db = mogoClient[f"{dateString}"]

    try:
        raw_data = indata.decode()
        
        band_Mac = raw_data[5:17]
        safe_Mac = raw_data[189:201]
        state = int(raw_data[97:99],16) # 1為舊手環, 2為新手環, 3為蓋德
        tmp = tmpIdentify(raw_data, state)
        sleep = int(raw_data[87:89],16)*60 + int(raw_data[89:91],16)
        raw_data_document = {
            # 協定換算方式:ex 血壓35~36 => 35*2-1=69 => 所以血壓的位置位於raw_data的第69個，有4個bytes，69~72為血壓的判讀區域，剩下的以此類推。
            'Time' : time,
            'state' : judgeState(raw_data), #確認封包狀態
            'raspberry_Mac' : raw_data[-2:],
            'safe_Mac' : raw_data[189:201],
            'safe_battery': int(raw_data[201:203],16),
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
            'HR' : int(raw_data[51:53],16),
            'Bloodpressure_SBP' : int((raw_data[53:55]),16),
            'Bloodpressure_DBP' : int((raw_data[55:57]),16),
            'Step' : int((raw_data[57:59] + raw_data[59:61]),16),
            'Mileage' : int((raw_data[61:63] + raw_data[63:65]),16)/1000,
            'Blood_oxygen' : int((raw_data[65:67]),16),
            'Calories' : int((raw_data[67:69] + raw_data[69:71]),16),
            'band_battery' : int(raw_data[85:87],16),
            'Temperature' : tmp[0:2] + '.' + tmp[2:4], # 體溫
            'Sleep' : sleep, # 單位:min
            'Nap' : int(raw_data[91:93],16),
            'SOS' : int(raw_data[93:95],16),
            'Button' : int(raw_data[95:97],16),
            'New&Old' : state,
            #----------------手環生化訊號(暫時沒用到)----------
            # 'Takemedicine1' : int(raw_data[113:115],16),
            # 'Takemedicine2' : int(raw_data[115:117],16),
            # 'Bloodsugar' : int(raw_data[117:119],16),
            # 'Lacticacid' : int(raw_data[119:121],16),
            #-----------------護身符--------------------------
            'ACC_X' : twosComplement_hex(raw_data[121:125])/512,
            'ACC_Y' : twosComplement_hex(raw_data[125:129])/512,
            'ACC_Z' : twosComplement_hex(raw_data[129:133])/512,
            'ACC_total' : twosComplement_hex(raw_data[133:137])/512,
            'roll16' : twosComplement_hex(raw_data[137:141])/100,
            'pitch16' : twosComplement_hex(raw_data[141:145])/100,
            'yaw16' : twosComplement_hex(raw_data[145:149])/100,
            'MAG_X' : twosComplement_hex(raw_data[149:153]),
            'MAG_Y' : twosComplement_hex(raw_data[153:157]),
            'MAG_Z' : twosComplement_hex(raw_data[157:161]),
            'MAG_total' : twosComplement_hex(raw_data[161:165]),
            'Press_16' : (twosComplement_hex(raw_data[165:169])+80000)/100,
            'Ambient temperature' : twosComplement_hex(raw_data[169:173])*0.0625, #環境溫度
            'Azimuth16' : twosComplement_hex(raw_data[175:179]),
            'Direction' : int(raw_data[179:181],16), #方位
            'RSSI' : twosComplement_hex(raw_data[181:185]), #護身符與Beacon的距離
            'Point' : int(raw_data[185:187],16), #Beacon定位點
            'Area' : int(raw_data[187:189],16) #靠近幾號Beacon
        }

        db[safe_Mac].insert_one(raw_data_document)
        db['savedevice'].insert_one(raw_data_document)
        print('================================================================')
        print(raw_data_document)
        print(len(raw_data))
        print(dot) # 出現錯誤的次數

    except:
        print('indata.decode() error')
        dot += 1