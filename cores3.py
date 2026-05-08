"""
M5Stack CoreS3 + EnV Pro Unit (BME688) → Azure IoT Hub
MicroPython / UIFlow2  |  Prof. Dr. Suat Can  |  HsH BDT-Demo

Display-Layout (320x240):
  ┌──────────────────────────────────────────┐
  │  ● WiFi  SSID-Name      ● Hub  OK / ERR  │  Statuszeile
  ├──────────────────────────────────────────┤
  │  ╔════════╗ ╔════════╗ ╔════════╗        │
  │  ║  23.4  ║ ║  48.1  ║ ║ 1013   ║        │
  │  ║   °C   ║ ║   %rH  ║ ║  hPa   ║        │
  │  ║  TEMP  ║ ║ FEUCHTE║ ║  DRUCK ║        │
  │  ╚════════╝ ╚════════╝ ╚════════╝        │
  ├──────────────────────────────────────────┤
  │  Seq: 42          Letzte Messung: 14:23  │  Fußzeile
  └──────────────────────────────────────────┘
"""

import network
import time
import json
import machine
import ustruct
from umqtt.simple import MQTTClient

# UIFlow2 / M5Stack MicroPython Display-Import
try:
    import M5
    from M5 import Lcd
    M5.begin()
    DISPLAY = Lcd
    HAS_DISPLAY = True
except ImportError:
    HAS_DISPLAY = False
    print("[Display] Kein M5-Modul – Display deaktiviert")

# ═══════════════════════════════════════════════════════════════
#  KONFIGURATION
# ═══════════════════════════════════════════════════════════════

WIFI_SSID       = "DEIN_WLAN_SSID"
WIFI_PASSWORD   = "DEIN_WLAN_PASSWORT"

IOT_HUB_HOST    = "DEIN-HUB.azure-devices.net"
DEVICE_ID       = "m5stack-cores3"
SAS_TOKEN       = "SharedAccessSignature sr=DEIN-HUB.azure-devices.net%2Fdevices%2Fm5stack-cores3&sig=XXX&se=9999999999"

I2C_SDA         = 2
I2C_SCL         = 1
I2C_FREQ        = 400_000
BME688_ADDR     = 0x77

SEND_INTERVAL_S = 30

# ═══════════════════════════════════════════════════════════════
#  DISPLAY – Farben & Layout (RGB565)
# ═══════════════════════════════════════════════════════════════

# Farben
C_BG        = 0x0D0D1A   # Hintergrund (sehr dunkelblau)
C_PANEL     = 0x1A1F35   # Karten-Hintergrund
C_BORDER    = 0x2A3050   # Karten-Rahmen
C_WHITE     = 0xFFFFFF
C_GRAY      = 0x7080A0
C_GREEN     = 0x00E676   # WiFi / Hub verbunden
C_RED       = 0xFF4444   # Fehler / getrennt
C_YELLOW    = 0xFFD740   # Verbinde...
C_TEMP      = 0xFF6B35   # Temperatur (Orange)
C_HUM       = 0x29B6F6   # Feuchte (Hellblau)
C_PRES      = 0xAB47BC   # Druck (Lila)
C_TOPBAR    = 0x12162B   # Statuszeile
C_FOOTBAR   = 0x12162B   # Fußzeile

# Display-Dimensionen CoreS3
SCR_W  = 320
SCR_H  = 240

# Layout-Konstanten
BAR_H      = 36   # Höhe Statuszeile / Fußzeile
CARD_Y     = BAR_H + 8
CARD_H     = SCR_H - BAR_H * 2 - 16
CARD_W     = 96
CARD_GAP   = 8
CARD_X1    = 8
CARD_X2    = CARD_X1 + CARD_W + CARD_GAP
CARD_X3    = CARD_X2 + CARD_W + CARD_GAP
CARD_R     = 6   # Eckradius


# ═══════════════════════════════════════════════════════════════
#  DISPLAY – Zeichenfunktionen
# ═══════════════════════════════════════════════════════════════

def d_clear():
    if not HAS_DISPLAY:
        return
    DISPLAY.fillScreen(C_BG)


def d_status_bar(wifi_ok: bool, wifi_ssid: str, hub_ok: bool, ip: str = ""):
    """Zeichnet die obere Statuszeile."""
    if not HAS_DISPLAY:
        return
    # Hintergrund Leiste
    DISPLAY.fillRect(0, 0, SCR_W, BAR_H, C_TOPBAR)
    # Trennlinie
    DISPLAY.drawLine(0, BAR_H - 1, SCR_W, BAR_H - 1, C_BORDER)

    # --- WiFi-Status (links) ---
    wifi_col = C_GREEN if wifi_ok else C_RED
    DISPLAY.fillCircle(14, BAR_H // 2, 5, wifi_col)
    DISPLAY.setTextColor(C_WHITE, C_TOPBAR)
    DISPLAY.setTextSize(1)
    label = wifi_ssid[:12] if wifi_ok else "No WiFi"
    DISPLAY.drawString(label, 24, 4)
    ip_label = ip if ip else ""
    DISPLAY.setTextColor(C_GRAY, C_TOPBAR)
    DISPLAY.drawString(ip_label[:15], 24, 18)

    # --- Hub-Status (rechts) ---
    hub_col = C_GREEN if hub_ok else C_RED
    hub_txt = "Hub OK" if hub_ok else "Hub ERR"
    DISPLAY.setTextColor(C_WHITE, C_TOPBAR)
    DISPLAY.drawString(hub_txt, SCR_W - 86, 4)
    DISPLAY.fillCircle(SCR_W - 10, BAR_H // 2, 5, hub_col)


def d_footer(seq: int, ts: int):
    """Zeichnet die untere Fußzeile."""
    if not HAS_DISPLAY:
        return
    fy = SCR_H - BAR_H
    DISPLAY.fillRect(0, fy, SCR_W, BAR_H, C_FOOTBAR)
    DISPLAY.drawLine(0, fy, SCR_W, fy, C_BORDER)

    DISPLAY.setTextColor(C_GRAY, C_FOOTBAR)
    DISPLAY.setTextSize(1)
    DISPLAY.drawString(f"Seq: {seq}", 8, fy + 6)

    # Zeitstempel aus Unix-Epoch (ohne RTC: zeigt Uptime-Sekunden)
    h = (ts // 3600) % 24
    m = (ts // 60) % 60
    s = ts % 60
    DISPLAY.drawString(f"Update: {h:02d}:{m:02d}:{s:02d}", SCR_W - 120, fy + 6)


def _draw_card(x: int, accent: int, title: str, value: str, unit: str):
    """Zeichnet eine Sensorwertkarte."""
    if not HAS_DISPLAY:
        return
    # Karten-Hintergrund
    DISPLAY.fillRoundRect(x, CARD_Y, CARD_W, CARD_H, CARD_R, C_PANEL)
    # Farbiger Akzentstreifen oben
    DISPLAY.fillRoundRect(x, CARD_Y, CARD_W, 4, CARD_R, accent)
    # Rahmen
    DISPLAY.drawRoundRect(x, CARD_Y, CARD_W, CARD_H, CARD_R, C_BORDER)

    # Titel (unten in der Karte)
    DISPLAY.setTextColor(accent, C_PANEL)
    DISPLAY.setTextSize(1)
    title_x = x + (CARD_W - len(title) * 6) // 2
    DISPLAY.drawString(title, title_x, CARD_Y + CARD_H - 18)

    # Wert (groß, zentriert)
    DISPLAY.setTextColor(C_WHITE, C_PANEL)
    DISPLAY.setTextSize(3)
    val_x = x + (CARD_W - len(value) * 18) // 2
    DISPLAY.drawString(value, val_x, CARD_Y + 20)

    # Einheit (mittig unter dem Wert)
    DISPLAY.setTextColor(C_GRAY, C_PANEL)
    DISPLAY.setTextSize(1)
    unit_x = x + (CARD_W - len(unit) * 6) // 2
    DISPLAY.drawString(unit, unit_x, CARD_Y + 60)


def d_sensor_cards(temp: float, hum: float, pres: float):
    """Aktualisiert alle drei Messkarten."""
    _draw_card(CARD_X1, C_TEMP, "TEMPERATUR", f"{temp:.1f}", "°C")
    _draw_card(CARD_X2, C_HUM,  "FEUCHTE",    f"{hum:.1f}", "%rH")
    _draw_card(CARD_X3, C_PRES, "DRUCK",      f"{pres:.0f}", "hPa")


def d_splash():
    """Bootscreen."""
    if not HAS_DISPLAY:
        return
    DISPLAY.fillScreen(C_BG)
    DISPLAY.setTextColor(C_WHITE, C_BG)
    DISPLAY.setTextSize(2)
    DISPLAY.drawString("M5Stack CoreS3", 40, 60)
    DISPLAY.setTextSize(1)
    DISPLAY.setTextColor(C_GRAY, C_BG)
    DISPLAY.drawString("BME688 + Azure IoT Hub", 50, 92)
    DISPLAY.drawString("Initialisiere...", 100, 120)


def d_connecting(step: str):
    """Zeigt Verbindungsfortschritt im Mittelteil an."""
    if not HAS_DISPLAY:
        return
    DISPLAY.fillRect(0, BAR_H, SCR_W, SCR_H - BAR_H * 2, C_BG)
    DISPLAY.setTextColor(C_YELLOW, C_BG)
    DISPLAY.setTextSize(1)
    DISPLAY.drawString(step, 20, SCR_H // 2 - 8)


# ═══════════════════════════════════════════════════════════════
#  WIFI
# ═══════════════════════════════════════════════════════════════

def connect_wifi(ssid: str, password: str, timeout_s: int = 20):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    d_status_bar(False, "Verbinde...", False)
    d_connecting(f"WiFi: {ssid[:20]}")

    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        d_status_bar(True, ssid, False, ip)
        print("[WiFi] Bereits verbunden:", wlan.ifconfig())
        return True, ip

    print(f"[WiFi] Verbinde mit '{ssid}' ...")
    wlan.connect(ssid, password)
    deadline = time.time() + timeout_s
    while not wlan.isconnected():
        if time.time() > deadline:
            d_status_bar(False, "Timeout", False)
            print("[WiFi] Timeout!")
            return False, ""
        time.sleep(0.5)

    ip = wlan.ifconfig()[0]
    d_status_bar(True, ssid, False, ip)
    print("[WiFi] Verbunden:", wlan.ifconfig())
    return True, ip


# ═══════════════════════════════════════════════════════════════
#  BME688-TREIBER
# ═══════════════════════════════════════════════════════════════

class BME688:
    _REG_ID        = 0xD0
    _REG_RESET     = 0xE0
    _REG_CTRL_HUM  = 0x72
    _REG_CTRL_MEAS = 0x74
    _REG_CONFIG    = 0x75
    _REG_GAS_WAIT0 = 0x64
    _REG_RES_HEAT0 = 0x5A
    _REG_CTRL_GAS1 = 0x71

    def __init__(self, i2c, addr: int = 0x77):
        self._i2c  = i2c
        self._addr = addr
        self._buf  = bytearray(20)

        chip_id = self._read_byte(self._REG_ID)
        if chip_id not in (0x60, 0x61):
            raise RuntimeError(f"BME688 nicht gefunden (chip_id=0x{chip_id:02X})")
        print(f"[BME688] chip_id=0x{chip_id:02X} - OK")

        self._write_byte(self._REG_RESET, 0xB6)
        time.sleep_ms(10)
        self._load_calibration()

        self._write_byte(self._REG_CTRL_HUM, 0x02)
        self._write_byte(self._REG_CONFIG,   0x0C)
        self._ctrl_meas = (0x02 << 5) | (0x03 << 2)
        self._configure_gas_heater(target_temp=300, ambient_temp=25, duration_ms=150)

    def measure(self) -> dict:
        self._write_byte(self._REG_CTRL_GAS1, 0x10)
        self._write_byte(self._REG_CTRL_MEAS, self._ctrl_meas | 0x01)
        for _ in range(40):
            time.sleep_ms(5)
            if self._read_byte(0x1D) & 0x80:
                break

        raw = self._i2c.readfrom_mem(self._addr, 0x1F, 13)
        adc_p     = (raw[0] << 12) | (raw[1] << 4) | (raw[2] >> 4)
        adc_t     = (raw[3] << 12) | (raw[4] << 4) | (raw[5] >> 4)
        adc_h     = (raw[6] << 8)  |  raw[7]
        adc_g     = (raw[8] << 2)  | (raw[9] >> 6)
        gas_range = raw[9] & 0x0F
        heat_stab = (raw[9] >> 4) & 0x01

        temp, t_fine = self._compensate_temperature(adc_t)
        pressure     = self._compensate_pressure(adc_p, t_fine)
        humidity     = self._compensate_humidity(adc_h, t_fine)
        gas_res      = self._compensate_gas(adc_g, gas_range) if heat_stab else None

        return {
            "temperature_c": round(temp, 2),
            "humidity_pct":  round(humidity, 2),
            "pressure_hpa":  round(pressure / 100, 2),
            "gas_ohm":       round(gas_res, 0) if gas_res else None,
            "heat_stable":   bool(heat_stab),
        }

    def _load_calibration(self):
        c1 = self._i2c.readfrom_mem(self._addr, 0x89, 25)
        c2 = self._i2c.readfrom_mem(self._addr, 0xE1, 16)

        self.par_t1 = ustruct.unpack_from("<H", c2, 8)[0]
        self.par_t2 = ustruct.unpack_from("<h", c1, 1)[0]
        self.par_t3 = ustruct.unpack_from("<b", c1, 3)[0]
        self.par_p1  = ustruct.unpack_from("<H", c1,  5)[0]
        self.par_p2  = ustruct.unpack_from("<h", c1,  7)[0]
        self.par_p3  = ustruct.unpack_from("<b", c1,  9)[0]
        self.par_p4  = ustruct.unpack_from("<h", c1, 11)[0]
        self.par_p5  = ustruct.unpack_from("<h", c1, 13)[0]
        self.par_p6  = ustruct.unpack_from("<b", c1, 16)[0]
        self.par_p7  = ustruct.unpack_from("<b", c1, 15)[0]
        self.par_p8  = ustruct.unpack_from("<h", c1, 19)[0]
        self.par_p9  = ustruct.unpack_from("<h", c1, 21)[0]
        self.par_p10 = ustruct.unpack_from("<B", c1, 23)[0]
        self.par_h1 = (c2[2] << 4) | (c2[1] & 0x0F)
        self.par_h2 = (c2[0] << 4) | (c2[1] >> 4)
        self.par_h3 = ustruct.unpack_from("<b", c2, 3)[0]
        self.par_h4 = ustruct.unpack_from("<b", c2, 4)[0]
        self.par_h5 = ustruct.unpack_from("<b", c2, 5)[0]
        self.par_h6 = c2[6]
        self.par_h7 = ustruct.unpack_from("<b", c2, 7)[0]
        self.par_g1 = ustruct.unpack_from("<b", c2, 12)[0]
        self.par_g2 = ustruct.unpack_from("<h", c2, 10)[0]
        self.par_g3 = ustruct.unpack_from("<b", c2, 13)[0]
        self.res_heat_range = (self._read_byte(0x02) & 0x30) >> 4
        self.res_heat_val   = ustruct.unpack_from("<b", bytearray([self._read_byte(0x00)]), 0)[0]
        self.range_sw_err   = (self._read_byte(0x04) & 0xF0) >> 4

    def _compensate_temperature(self, adc_t):
        var1   = (adc_t / 8) - (self.par_t1 * 2)
        var2   = (var1 * self.par_t2) / 2048
        var3   = ((var1 / 2) ** 2) / 4096 * self.par_t3 / 16384
        t_fine = var2 + var3
        return t_fine / 5120, t_fine

    def _compensate_pressure(self, adc_p, t_fine):
        var1 = (t_fine / 2) - 64000
        var2 = var1 * var1 * self.par_p6 / 131072
        var2 = var2 + (var1 * self.par_p5 * 2)
        var2 = (var2 / 4) + (self.par_p4 * 65536)
        var1 = (self.par_p3 * var1 * var1 / 16384 + self.par_p2 * var1) / 524288
        var1 = (1 + var1 / 32768) * self.par_p1
        if var1 == 0:
            return 0
        pres = 1048576 - adc_p
        pres = ((pres - (var2 / 4096)) * 6250) / var1
        var1 = self.par_p9 * pres * pres / 2147483648
        var2 = pres * self.par_p8 / 32768
        return pres + (var1 + var2 + self.par_p7) / 16

    def _compensate_humidity(self, adc_h, t_fine):
        temp = t_fine / 5120
        var1 = adc_h - (self.par_h1 * 16) - ((temp * self.par_h3) / 200) * 16
        var2 = var1 * self.par_h2 / 262144 * (1 + self.par_h4 / 16384 * temp + self.par_h5 / 1048576 * temp * temp)
        var3 = self.par_h6 / 16384
        var4 = self.par_h7 / 2097152
        return max(0.0, min(100.0, var2 + (var3 + var4 * temp) * var2 * var2))

    def _compensate_gas(self, adc_g, gas_range):
        _K1 = [0.0,0.0,0.0,0.0,0.0,-1.0,0.0,-0.8,0.0,0.0,-0.2,-0.5,0.0,-1.0,0.0,0.0]
        _K2 = [0.0,0.0,0.0,0.0,0.1,0.7,0.0,-0.8,-0.1,0.0,0.0,0.0,0.0,0.0,0.0,0.0]
        var1 = (1340 + 5 * self.range_sw_err) * _K1[gas_range] / 65536
        var2 = ((adc_g << 15) - 16777216) + var1
        var3 = _K2[gas_range] * var2 / 512
        return (var3 + var2 / 2) / (1 << gas_range)

    def _configure_gas_heater(self, target_temp, ambient_temp, duration_ms):
        var1 = self.par_g1 / 16 + 49
        var2 = self.par_g2 / 32768 * 0.0005 + 0.00235
        var3 = self.par_g3 / 1024
        var4 = var1 * (1 + var2 * target_temp)
        var5 = var4 + var3 * ambient_temp
        res_heat = int(3.4 * (var5 * (4 / (4 + self.res_heat_range)) * (1 / (1 + self.res_heat_val * 0.002)) - 25))
        res_heat = max(0, min(255, res_heat))
        gas_dur = duration_ms
        if gas_dur >= 0xFC0:
            gas_dur_reg = 0xFF
        else:
            factor = 0
            while gas_dur > 0x3F:
                gas_dur //= 4
                factor += 1
            gas_dur_reg = gas_dur | (factor << 6)
        self._write_byte(self._REG_RES_HEAT0, res_heat)
        self._write_byte(self._REG_GAS_WAIT0, gas_dur_reg)

    def _read_byte(self, reg):
        self._i2c.readfrom_mem_into(self._addr, reg, self._buf, addrsize=8)
        return self._buf[0]

    def _write_byte(self, reg, value):
        self._i2c.writeto_mem(self._addr, reg, bytes([value]))


# ═══════════════════════════════════════════════════════════════
#  AZURE IOT HUB – MQTT
# ═══════════════════════════════════════════════════════════════

def build_mqtt_client(wifi_ssid: str, ip: str):
    mqtt_user = f"{IOT_HUB_HOST}/{DEVICE_ID}/?api-version=2021-04-12"
    topic_pub = f"devices/{DEVICE_ID}/messages/events/"
    topic_sub = f"devices/{DEVICE_ID}/messages/devicebound/#"

    d_connecting("Azure IoT Hub verbinden...")
    d_status_bar(True, wifi_ssid, False, ip)

    client = MQTTClient(
        client_id  = DEVICE_ID,
        server     = IOT_HUB_HOST,
        port       = 8883,
        user       = mqtt_user,
        password   = SAS_TOKEN,
        keepalive  = 120,
        ssl        = True,
        ssl_params = {"server_hostname": IOT_HUB_HOST},
    )

    def on_message(topic, msg):
        print(f"[IoT Hub down] {topic.decode()}: {msg.decode()}")

    client.set_callback(on_message)
    print("[MQTT] Verbinde mit Azure IoT Hub ...")
    client.connect()
    client.subscribe(topic_sub)
    print(f"[MQTT] Verbunden. Topic: {topic_pub}")
    return client, topic_pub


# ═══════════════════════════════════════════════════════════════
#  HAUPTPROGRAMM
# ═══════════════════════════════════════════════════════════════

def main():
    # Bootscreen
    d_splash()
    time.sleep(1)
    d_clear()
    d_status_bar(False, "...", False)

    # 1. WiFi
    ok, ip = connect_wifi(WIFI_SSID, WIFI_PASSWORD)
    if not ok:
        machine.reset()

    # 2. BME688
    d_connecting("Sensor initialisieren...")
    i2c = machine.I2C(0, sda=machine.Pin(I2C_SDA), scl=machine.Pin(I2C_SCL), freq=I2C_FREQ)
    print("[I2C] Scan:", [hex(a) for a in i2c.scan()])
    sensor = BME688(i2c, addr=BME688_ADDR)

    # 3. Azure IoT Hub
    hub_ok = False
    try:
        mqtt_client, topic_pub = build_mqtt_client(WIFI_SSID, ip)
        hub_ok = True
    except Exception as e:
        print(f"[MQTT] Verbindungsfehler: {e}")
        d_status_bar(True, WIFI_SSID, False, ip)

    # Leeres Dashboard aufbauen
    d_status_bar(True, WIFI_SSID, hub_ok, ip)
    d_sensor_cards(0.0, 0.0, 0.0)
    d_footer(0, time.time())

    # 4. Telemetrie-Schleife
    seq       = 0
    last_send = time.time() - SEND_INTERVAL_S

    while True:
        # Eingehende Nachrichten prüfen
        if hub_ok:
            try:
                mqtt_client.check_msg()
            except Exception as e:
                print(f"[MQTT] check_msg: {e}")
                hub_ok = False
                d_status_bar(True, WIFI_SSID, False, ip)

        if time.time() - last_send >= SEND_INTERVAL_S:
            last_send = time.time()
            seq += 1

            # Messen
            try:
                data = sensor.measure()
            except Exception as e:
                print(f"[BME688] Messfehler: {e}")
                time.sleep(1)
                continue

            temp = data["temperature_c"]
            hum  = data["humidity_pct"]
            pres = data["pressure_hpa"]

            # Display aktualisieren
            d_sensor_cards(temp, hum, pres)
            d_footer(seq, time.time())

            print(f"[Telemetrie #{seq}] T={temp}°C  H={hum}%  P={pres}hPa")

            # Senden
            if hub_ok:
                payload  = {
                    "deviceId":      DEVICE_ID,
                    "seq":           seq,
                    "timestamp":     time.time(),
                    "temperature":   temp,
                    "humidity":      hum,
                    "pressure":      pres,
                    "gasResistance": data["gas_ohm"],
                    "heatStable":    data["heat_stable"],
                }
                try:
                    mqtt_client.publish(topic_pub, json.dumps(payload), qos=0)
                except Exception as e:
                    print(f"[MQTT] Publish fehlgeschlagen: {e} - reconnect...")
                    hub_ok = False
                    d_status_bar(True, WIFI_SSID, False, ip)
                    try:
                        mqtt_client.disconnect()
                    except Exception:
                        pass
                    time.sleep(3)
                    try:
                        mqtt_client, topic_pub = build_mqtt_client(WIFI_SSID, ip)
                        hub_ok = True
                        d_status_bar(True, WIFI_SSID, True, ip)
                    except Exception as e2:
                        print(f"[MQTT] Reconnect fehlgeschlagen: {e2}")

        time.sleep(1)


# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    main()
