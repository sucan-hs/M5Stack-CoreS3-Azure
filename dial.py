"""
M5Stack DIAL (v1.1) + EnV Pro Unit (BME688) → Azure IoT Hub
MicroPython / UIFlow2  |  Prof. Dr. Suat Can  |  HsH BDT-Demo

Display: 1.28" rund, GC9A01, 240×240 px (nur Kreisfläche sichtbar)
Encoder: Drehen → Sensor wechseln (T / H / P / Gas)
         Drücken → sofortige Messung + Senden

Display-Layout (Kreis ⌀240):
  ┌──────────────────────────────┐
  │     ● WiFi        Hub ●      │  ← Statusdots (Außenring oben)
  │        TEMPERATUR            │  ← Sensorname
  │                              │
  │           23.4               │  ← Hauptwert (groß)
  │            °C                │  ← Einheit
  │                              │
  │     48%rH    1013hPa         │  ← Sekundärwerte
  │        ◄ drehen ►            │  ← Encoderhinweis
  └──────────────────────────────┘

Außenbogen:
  - Linke Hälfte (grün/rot):  WiFi-Status
  - Rechte Hälfte (grün/rot): IoT-Hub-Status
  - Farbiger Akzentring:      Aktiver Sensor (Orange/Blau/Lila/Grün)
"""

import network
import time
import json
import machine
import ustruct
from umqtt.simple import MQTTClient

# UIFlow2 / M5Stack MicroPython
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
DEVICE_ID       = "m5dial-v1"
SAS_TOKEN       = "SharedAccessSignature sr=DEIN-HUB.azure-devices.net%2Fdevices%2Fm5dial-v1&sig=XXX&se=9999999999"

# I2C – EnV Pro Unit am DIAL PORT.A (Grove)
#   DIAL v1.1 PORT.A: SDA = GPIO 2, SCL = GPIO 1
I2C_SDA     = 2
I2C_SCL     = 1
I2C_FREQ    = 400_000
BME688_ADDR = 0x77   # SDO an VCC→0x77 | SDO an GND→0x76

# Encoder-Pins DIAL v1.1
ENC_CLK = 40   # Encoder A (CLK)
ENC_DT  = 41   # Encoder B (DT)
ENC_SW  = 42   # Encoder Taster (SW)

SEND_INTERVAL_S = 30

# ═══════════════════════════════════════════════════════════════
#  DISPLAY – Farben & Konstanten (RGB565)
# ═══════════════════════════════════════════════════════════════

C_BG      = 0x0A0B14   # Hintergrund (tief dunkel)
C_WHITE   = 0xFFFFFF
C_GRAY    = 0x607090
C_GREEN   = 0x00E676
C_RED     = 0xFF4444
C_YELLOW  = 0xFFD740

# Sensor-Akzentfarben
SENSOR_COLORS = [0xFF6B35, 0x29B6F6, 0xAB47BC, 0x66BB6A]  # T, H, P, Gas
SENSOR_NAMES  = ["TEMPERATUR", "FEUCHTE", "LUFTDRUCK", "GAS"]
SENSOR_UNITS  = ["°C", "%rH", "hPa", "kΩ"]

# Runddisplay-Mittelpunkt & Radien
CX, CY = 120, 120
R_OUTER   = 118   # äußerster sichtbarer Rand
R_ACCENT  = 115   # Akzentring (Sensorfarbe)
R_STATUS  = 108   # WiFi/Hub-Statusbogen
R_CONTENT = 100   # Inhaltsfläche (Innenkreis)


# ═══════════════════════════════════════════════════════════════
#  DISPLAY – Zeichenfunktionen (rundes GC9A01-Display)
# ═══════════════════════════════════════════════════════════════

def _arc(x, y, r_in, r_out, a0, a1, color):
    """
    Zeichnet einen Kreisbogen (Füllbereich) von a0 bis a1 Grad.
    Nutzt M5.Lcd.fillArc – UIFlow2-spezifisch.
    Fallback: Pixel-Ring manuell setzen.
    """
    if not HAS_DISPLAY:
        return
    try:
        DISPLAY.fillArc(x, y, r_out, r_in, a0, a1, color)
    except AttributeError:
        # Fallback: manuelle Punktreihe entlang des Bogens
        import math
        for deg in range(a0, a1, 2):
            rad = math.radians(deg)
            for r in range(r_in, r_out):
                px = int(x + r * math.cos(rad))
                py = int(y + r * math.sin(rad))
                DISPLAY.drawPixel(px, py, color)


def d_clear():
    if not HAS_DISPLAY:
        return
    DISPLAY.fillScreen(C_BG)


def d_base_circle(accent_color: int):
    """Zeichnet den runden Basishintergrund mit farbigem Akzentring."""
    if not HAS_DISPLAY:
        return
    # Schwarzer Außenring (Maskierung der Ecken)
    DISPLAY.fillRect(0, 0, 240, 240, 0x000000)
    # Dunkelblauer Hintergrundkreis
    DISPLAY.fillCircle(CX, CY, R_STATUS - 1, C_BG)
    # Farbiger Akzentring (voller Ring)
    _arc(CX, CY, R_STATUS, R_ACCENT, 0, 360, accent_color)
    # Dunkel-Innenkreis übermalen → Akzentring bleibt als schmaler Streifen
    DISPLAY.fillCircle(CX, CY, R_STATUS - 1, C_BG)


def d_status_arcs(wifi_ok: bool, hub_ok: bool, accent_color: int):
    """
    Zeichnet den zweigeteilten Statusring (außen):
      - Linke Hälfte (270°→90°):  WiFi
      - Rechte Hälfte (90°→270°): IoT Hub
    """
    if not HAS_DISPLAY:
        return
    wifi_col = C_GREEN if wifi_ok  else C_RED
    hub_col  = C_GREEN if hub_ok   else C_RED

    # Linker Bogen (WiFi): 180°→360° (= untere/linke Halbebene)
    _arc(CX, CY, R_ACCENT, R_OUTER, 180, 360, wifi_col)
    # Rechter Bogen (Hub): 0°→180°
    _arc(CX, CY, R_ACCENT, R_OUTER, 0, 180, hub_col)

    # Schmale Trennfuge oben & unten (schwarz)
    DISPLAY.fillRect(CX - 2, 0,  4, 8,   0x000000)
    DISPLAY.fillRect(CX - 2, 232, 4, 8,  0x000000)

    # Farbiger Akzent-Innenring
    _arc(CX, CY, R_STATUS, R_ACCENT, 0, 360, accent_color)
    DISPLAY.fillCircle(CX, CY, R_STATUS - 1, C_BG)


def d_sensor_view(idx: int, values: list, seq: int):
    """
    Zeigt den aktiven Sensorwert groß im Zentrum.
    values = [temp, hum, pres, gas_kohm]
    idx    = 0..3 (aktiver Sensor)
    """
    if not HAS_DISPLAY:
        return

    accent = SENSOR_COLORS[idx]
    name   = SENSOR_NAMES[idx]
    unit   = SENSOR_UNITS[idx]
    val    = values[idx]

    # Inhaltsfläche leeren
    DISPLAY.fillCircle(CX, CY, R_STATUS - 2, C_BG)

    # Sensorname (oben, klein)
    DISPLAY.setTextColor(accent, C_BG)
    DISPLAY.setTextSize(1)
    name_x = CX - len(name) * 3
    DISPLAY.drawString(name, name_x, 54)

    # Hauptwert (mittig, sehr groß)
    DISPLAY.setTextColor(C_WHITE, C_BG)
    DISPLAY.setTextSize(4)
    val_str = f"{val:.1f}" if val is not None else "---"
    if idx == 2:   # Druck: keine Dezimale
        val_str = f"{val:.0f}" if val is not None else "----"
    if idx == 3:   # Gas in kΩ
        val_str = f"{val/1000:.1f}" if val is not None else "--"
    val_x = CX - len(val_str) * 12
    DISPLAY.drawString(val_str, val_x, 90)

    # Einheit
    DISPLAY.setTextColor(accent, C_BG)
    DISPLAY.setTextSize(2)
    unit_x = CX - len(unit) * 6
    DISPLAY.drawString(unit, unit_x, 136)

    # Sekundärwerte (kleine Zeile unten)
    DISPLAY.setTextColor(C_GRAY, C_BG)
    DISPLAY.setTextSize(1)

    others = [(i, values[i]) for i in range(4) if i != idx and values[i] is not None]
    secondary = []
    for i, v in others[:2]:
        u = SENSOR_UNITS[i]
        s = f"{v:.0f}{u}" if i in (2,) else f"{v:.1f}{u}"
        secondary.append(s)

    if len(secondary) >= 2:
        DISPLAY.drawString(secondary[0], 36,  172)
        DISPLAY.drawString(secondary[1], 138, 172)
    elif len(secondary) == 1:
        DISPLAY.drawString(secondary[0], CX - len(secondary[0])*3, 172)

    # Seq-Nummer (winzig, ganz unten)
    DISPLAY.setTextColor(0x2A3550, C_BG)
    DISPLAY.drawString(f"#{seq}", CX - 10, 192)

    # Encoder-Hinweis
    DISPLAY.setTextColor(0x2A3550, C_BG)
    DISPLAY.drawString("< drehen >", CX - 28, 208)


def d_splash():
    """Bootscreen auf dem Runddisplay."""
    if not HAS_DISPLAY:
        return
    DISPLAY.fillScreen(0x000000)
    DISPLAY.fillCircle(CX, CY, R_OUTER, 0x0A0B18)
    _arc(CX, CY, R_ACCENT, R_OUTER, 0, 360, 0x29B6F6)
    DISPLAY.fillCircle(CX, CY, R_ACCENT - 1, 0x0A0B18)

    DISPLAY.setTextColor(C_WHITE, 0x0A0B18)
    DISPLAY.setTextSize(1)
    DISPLAY.drawString("M5Stack DIAL", 68, 88)
    DISPLAY.setTextColor(0x607090, 0x0A0B18)
    DISPLAY.drawString("BME688", 96, 106)
    DISPLAY.drawString("Azure IoT Hub", 62, 122)


def d_progress(pct: int, label: str, color: int = 0x29B6F6):
    """Zeichnet einen Fortschritts-Bogen (Ladebalken)."""
    if not HAS_DISPLAY:
        return
    DISPLAY.fillCircle(CX, CY, R_STATUS - 1, C_BG)
    if pct > 0:
        angle = int(3.6 * pct)   # 0-100% → 0-360°
        _arc(CX, CY, R_ACCENT, R_OUTER, 270, 270 + angle, color)
        DISPLAY.fillCircle(CX, CY, R_ACCENT - 1, C_BG)

    DISPLAY.setTextColor(color, C_BG)
    DISPLAY.setTextSize(1)
    lbl_x = CX - len(label) * 3
    DISPLAY.drawString(label, lbl_x, 112)
    DISPLAY.setTextColor(0x2A3550, C_BG)
    DISPLAY.drawString(f"{pct}%", CX - 10, 128)


# ═══════════════════════════════════════════════════════════════
#  ENCODER – Dreh-Handler
# ═══════════════════════════════════════════════════════════════

class RotaryEncoder:
    """
    Einfacher Polling-Decoder für quadratischen Encoder (KY-040-kompatibel).
    Gibt delta = +1 (rechts) oder -1 (links) zurück.
    """
    def __init__(self, pin_clk: int, pin_dt: int, pin_sw: int):
        self._clk    = machine.Pin(pin_clk, machine.Pin.IN, machine.Pin.PULL_UP)
        self._dt     = machine.Pin(pin_dt,  machine.Pin.IN, machine.Pin.PULL_UP)
        self._sw     = machine.Pin(pin_sw,  machine.Pin.IN, machine.Pin.PULL_UP)
        self._last   = self._clk.value()
        self._sw_was = 1

    def poll(self):
        """
        Gibt zurück:
          ('rotate', +1) / ('rotate', -1) wenn gedreht
          ('press', None)                  wenn gedrückt
          (None, None)                     sonst
        """
        # Drehen
        cur = self._clk.value()
        if cur != self._last:
            self._last = cur
            if cur == 0:
                delta = -1 if self._dt.value() == 0 else 1
                return ('rotate', delta)

        # Drücken (fallende Flanke)
        sw = self._sw.value()
        if sw == 0 and self._sw_was == 1:
            self._sw_was = 0
            return ('press', None)
        if sw == 1:
            self._sw_was = 1

        return (None, None)


# ═══════════════════════════════════════════════════════════════
#  BME688-TREIBER (identisch mit CoreS3-Version)
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
#  WIFI
# ═══════════════════════════════════════════════════════════════

def connect_wifi(ssid: str, password: str, timeout_s: int = 20):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    d_progress(5, "WiFi...")
    if wlan.isconnected():
        print("[WiFi] Bereits verbunden:", wlan.ifconfig())
        return True, wlan.ifconfig()[0]

    print(f"[WiFi] Verbinde mit '{ssid}' ...")
    wlan.connect(ssid, password)
    deadline = time.time() + timeout_s
    step = 10
    while not wlan.isconnected():
        if time.time() > deadline:
            print("[WiFi] Timeout!")
            return False, ""
        step = min(step + 3, 45)
        d_progress(step, "WiFi...", C_RED if step > 40 else 0x29B6F6)
        time.sleep(0.5)

    ip = wlan.ifconfig()[0]
    d_progress(50, "WiFi OK", C_GREEN)
    time.sleep_ms(400)
    print("[WiFi] Verbunden:", wlan.ifconfig())
    return True, ip


# ═══════════════════════════════════════════════════════════════
#  AZURE IOT HUB – MQTT
# ═══════════════════════════════════════════════════════════════

def build_mqtt_client():
    mqtt_user = f"{IOT_HUB_HOST}/{DEVICE_ID}/?api-version=2021-04-12"
    topic_pub = f"devices/{DEVICE_ID}/messages/events/"
    topic_sub = f"devices/{DEVICE_ID}/messages/devicebound/#"

    d_progress(60, "Azure Hub...", 0xAB47BC)

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
        print(f"[IoT Hub ↓] {topic.decode()}: {msg.decode()}")

    client.set_callback(on_message)
    print("[MQTT] Verbinde mit Azure IoT Hub ...")
    client.connect()
    client.subscribe(topic_sub)
    print(f"[MQTT] Verbunden → {topic_pub}")
    return client, topic_pub


# ═══════════════════════════════════════════════════════════════
#  HAUPTPROGRAMM
# ═══════════════════════════════════════════════════════════════

def main():
    # Bootscreen
    d_splash()
    time.sleep_ms(800)

    # 1. WiFi
    wifi_ok, ip = connect_wifi(WIFI_SSID, WIFI_PASSWORD)
    if not wifi_ok:
        machine.reset()

    # 2. BME688
    d_progress(52, "Sensor...", 0xFF6B35)
    i2c = machine.I2C(0, sda=machine.Pin(I2C_SDA), scl=machine.Pin(I2C_SCL), freq=I2C_FREQ)
    print("[I2C] Scan:", [hex(a) for a in i2c.scan()])
    sensor = BME688(i2c, addr=BME688_ADDR)
    d_progress(58, "Sensor OK", C_GREEN)
    time.sleep_ms(300)

    # 3. Azure IoT Hub
    hub_ok = False
    try:
        mqtt_client, topic_pub = build_mqtt_client()
        hub_ok = True
        d_progress(100, "Verbunden!", C_GREEN)
        time.sleep_ms(600)
    except Exception as e:
        print(f"[MQTT] Verbindungsfehler: {e}")
        d_progress(65, "Hub ERR", C_RED)
        time.sleep_ms(800)

    # 4. Encoder initialisieren
    encoder = RotaryEncoder(ENC_CLK, ENC_DT, ENC_SW)
    sensor_idx = 0       # 0=Temp, 1=Hum, 2=Pres, 3=Gas
    values = [None, None, None, None]

    # Erstes Display-Bild aufbauen
    d_base_circle(SENSOR_COLORS[sensor_idx])
    d_status_arcs(wifi_ok, hub_ok, SENSOR_COLORS[sensor_idx])
    d_sensor_view(sensor_idx, [0.0, 0.0, 0.0, 0.0], 0)

    seq       = 0
    last_send = time.time() - SEND_INTERVAL_S  # sofort messen
    redraw    = False

    # 5. Hauptschleife
    while True:
        # Encoder abfragen
        ev, delta = encoder.poll()
        if ev == 'rotate':
            sensor_idx = (sensor_idx + delta) % 4
            redraw = True
        elif ev == 'press':
            # Sofortige Messung erzwingen
            last_send = time.time() - SEND_INTERVAL_S

        # Eingehende MQTT-Nachrichten
        if hub_ok:
            try:
                mqtt_client.check_msg()
            except Exception as e:
                print(f"[MQTT] check_msg: {e}")
                hub_ok = False
                redraw = True

        # Messung & Senden
        if time.time() - last_send >= SEND_INTERVAL_S:
            last_send = time.time()
            seq += 1

            try:
                data    = sensor.measure()
                values  = [
                    data["temperature_c"],
                    data["humidity_pct"],
                    data["pressure_hpa"],
                    data["gas_ohm"],
                ]
                redraw = True
            except Exception as e:
                print(f"[BME688] Messfehler: {e}")

            # Senden
            if hub_ok and values[0] is not None:
                payload = {
                    "deviceId":      DEVICE_ID,
                    "seq":           seq,
                    "timestamp":     time.time(),
                    "temperature":   values[0],
                    "humidity":      values[1],
                    "pressure":      values[2],
                    "gasResistance": values[3],
                    "sensorView":    sensor_idx,
                }
                try:
                    mqtt_client.publish(topic_pub, json.dumps(payload), qos=0)
                    print(f"[Telemetrie #{seq}] T={values[0]}°C H={values[1]}% P={values[2]}hPa")
                except Exception as e:
                    print(f"[MQTT] Publish fehlgeschlagen: {e} – reconnect ...")
                    hub_ok = False
                    try:
                        mqtt_client.disconnect()
                    except Exception:
                        pass
                    time.sleep(3)
                    try:
                        mqtt_client, topic_pub = build_mqtt_client()
                        hub_ok = True
                    except Exception as e2:
                        print(f"[MQTT] Reconnect fehlgeschlagen: {e2}")
                    redraw = True

        # Display nur bei Änderung neu zeichnen
        if redraw:
            redraw = False
            accent = SENSOR_COLORS[sensor_idx]
            d_status_arcs(wifi_ok, hub_ok, accent)
            safe_vals = [v if v is not None else 0.0 for v in values]
            d_sensor_view(sensor_idx, safe_vals, seq)

        time.sleep_ms(20)   # ~50 Hz Encoder-Polling


# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    main()