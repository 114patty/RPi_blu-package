import serial
import queue
import time
import datetime
import socket

ser = serial.Serial('/dev/ttyAMA0', 115200)    #Open port with baud rate
uart_read_queue = queue.Queue(maxsize=50)
uart_write_queue = queue.Queue()
HOST = '114.32.77.107' #serverIP
PORT = 8001 #server port

server_addr = (HOST, PORT)
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def decode_data(data):
    clear_data = data[:]
    now = datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=8)))
    packet = clear_data + str(datetime.datetime.utcnow() + datetime.timedelta(hours = 8)) + 'r1' 
    return packet

class Uart_Read:
    def __init__(self, read_queue, write_queue, ser):
        self.read_queue = read_queue
        self.write_queue = write_queue
        self.ser = ser
    def run(self):
        while True:
            try:
                data = self.ser.readline().decode()
                if (uart_write_queue.qsize() > 0):
                    uart_write_data = uart_write_queue.get()
                    ser.write(uart_write_data.decode('hex'))

                packet = decode_data(data)
                print(len(packet))
                if len(packet) == 233:                      # 辨識封包是否為手環封包
                    """主要程式"""

            except:
                print('error')
    
dd = Uart_Read(uart_read_queue, uart_write_queue, ser)
print("start")
dd.run()