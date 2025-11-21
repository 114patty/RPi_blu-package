# mqtt_status.py
import json, time, uuid, threading
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

class MQTTStatus:
    def __init__(self, host, port=1883, username=None, password=None, keepalive=30, hb_sec=60):
        self.device_id = hex(uuid.getnode())[2:].upper()
        self.host, self.port, self.keepalive = host, port, keepalive
        self.username, self.password = username, password
        self.hb_sec = hb_sec
        self.status_topic = f"devices/{self.device_id}/status"
        self.hb_topic     = f"devices/{self.device_id}/heartbeat"
        self._stop = threading.Event()

        self.client = mqtt.Client(client_id=f"pi-{self.device_id}", clean_session=True)
        if username and password:
            self.client.username_pw_set(username, password)

        # ❶ 遺囑：非正常斷線時，Broker 自動發布 offline（且保留）
        self.client.will_set(self.status_topic, json.dumps({"status":"offline"}), qos=1, retain=True)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    def _now(self):
        return datetime.now(timezone.utc).isoformat()

    def _on_connect(self, client, userdata, flags, rc):
        print("MQTT connected rc:", rc)
        # ❷ 上線宣告（保留），讓監控端一訂閱就能看到目前狀態
        self.client.publish(self.status_topic, json.dumps({"status":"online","ts":self._now()}), qos=1, retain=True)

    def _on_disconnect(self, client, userdata, rc):
        print("MQTT disconnected rc:", rc)

    def _hb_loop(self):
        while not self._stop.wait(self.hb_sec):
            # ❸ 心跳：非保留，用來看延遲與最後活動時間
            self.client.publish(self.hb_topic, json.dumps({"ts": self._now()}), qos=0, retain=False)

    def start(self):
        self.client.connect(self.host, self.port, self.keepalive)
        self.client.loop_start()
        self._t = threading.Thread(target=self._hb_loop, daemon=True)
        self._t.start()

    def stop(self):
        # 優雅下線：主動送 offline 覆蓋 retained
        self.client.publish(self.status_topic, json.dumps({"status":"offline","ts":self._now()}), qos=1, retain=True)
        self._stop.set()
        self.client.disconnect()
        self.client.loop_stop()
