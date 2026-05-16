# M5Stack CoreS3 / DIAL v1.1 + BME688 → Azure IoT Hub

MicroPython-Anwendung für **M5Stack CoreS3** oder **M5Stack DIAL v1.1** mit **EnV Pro Unit (BME688-Sensor)** zur Erfassung von Umweltdaten und Übertragung an **Azure IoT Hub**.

| Gerät | Display | Steuerung | Datei |
|-------|---------|-----------|-------|
| CoreS3 | 3.5" rechteckig (320×240) | Touch | `cores3.py` |
| DIAL v1.1 | 1.28" rund (240×240) | Drehencoder | `dial.py` |

## Überblick

Dieses Projekt liest Temperatur, Luftfeuchtigkeit, Luftdruck und Gaswiderstand vom BME688-Sensor und sendet die Daten per MQTT an Azure IoT Hub.

### CoreS3 (rechteckiges Display)

Die Messwerte werden auf dem 320×240 Display in Echtzeit angezeigt:

```
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
```

### DIAL v1.1 (rundes Display)

Interaktives Dashboard auf dem 240×240 px Runddisplay mit Encoder-Steuerung:

```
       ┌──────────────────┐
    ╭──│    ● WiFi  Hub ● │──╮  ← Statusbögen (Außenring)
   ╱   │     TEMPERATUR     │   ╲
  │    │                    │    │
  │    │        23.4        │    │  ← Hauptwert (groß)
  │    │         °C         │    │  ← Einheit
  │    │                    │    │
  │    │   48%rH  1013hPa   │    │  ← Sekundärwerte
   ╲   │     ◄ drehen ►     │   ╱
    ╰──└──────────────────┘──╯
```

**Encoder-Steuerung:**
- **Drehen**: Sensor wechseln (Temperatur → Feuchte → Druck → Gas)
- **Drücken**: Sofortige Messung + Senden auslösen

Der farbige Akzentring zeigt den aktiven Sensor an:
- 🟠 Orange = Temperatur
- 🔵 Blau = Feuchte
- 🟣 Lila = Druck
- 🟢 Grün = Gaswiderstand

## Hardware

### Komponenten

| Komponente | Beschreibung | Verbindung |
|------------|--------------|------------|
| M5Stack CoreS3 | ESP32-S3 mit 3.5" Touch-Display (320×240) | - |
| M5Stack DIAL v1.1 | ESP32-S3 mit 1.28" Runddisplay + Encoder | - |
| EnV Pro Unit | BME688 Sensor (Temp, Feuchte, Druck, Gas) | I2C Port.A |

### I2C-Pins (beide Geräte)

| Signal | GPIO | Funktion |
|--------|------|----------|
| SDA | GPIO 2 | I2C Daten |
| SCL | GPIO 1 | I2C Takt |
| Adresse | 0x77 | BME688 I2C-Adresse |

### DIAL v1.1 Encoder-Pins

| Signal | GPIO | Funktion |
|--------|------|----------|
| ENC_CLK | 40 | Encoder A (CLK) |
| ENC_DT | 41 | Encoder B (DT) |
| ENC_SW | 42 | Encoder Taster (SW) |

## Software-Voraussetzungen

- [UIFlow2](https://uiflow2.m5stack.com/) oder MicroPython für CoreS3
- `umqtt.simple` Bibliothek (in UIFlow2 enthalten)

## Konfiguration

Bearbeiten Sie die Konfigurationsvariablen in der entsprechenden Datei (`cores3.py` oder `dial.py`):

```python
# WLAN
WIFI_SSID       = "DEIN_WLAN_SSID"
WIFI_PASSWORD   = "DEIN_WLAN_PASSWORT"

# Azure IoT Hub
IOT_HUB_HOST    = "DEIN-HUB.azure-devices.net"
DEVICE_ID       = "m5stack-cores3"  # oder "m5dial-v1"
SAS_TOKEN       = "SharedAccessSignature sr=..."

# Intervall (Sekunden)
SEND_INTERVAL_S = 30
```

## Azure IoT Hub Einrichtung

1. Erstellen Sie einen IoT Hub in [Azure Portal](https://portal.azure.com)
2. Registrieren Sie ein neues Gerät unter *Geräteverwaltung → Geräte*
3. Generieren Sie ein SAS-Token:
   ```bash
   az iot hub generate-sas-token --device-id m5stack-cores3 --hub-name DEIN-HUB --duration 3600
   ```
4. Kopieren Sie das Token in die `SAS_TOKEN` Variable

## Verwendung

1. Kopieren Sie die passende Datei als `main.py` auf das Gerät:
   - **CoreS3**: `cores3.py` → `main.py`
   - **DIAL v1.1**: `dial.py` → `main.py`
2. Flashen Sie mit [M5Burner](https://docs.m5stack.com/en/download) oder UIFlow2
3. Das Gerät verbindet sich automatisch mit WLAN und Azure IoT Hub
4. Sensorwerte werden alle 30 Sekunden gesendet

### DIAL v1.1 Interaktion

- **Drehen**: Zwischen den 4 Sensoransichten wechseln
- **Drücken**: Sofortige Messung und Übertragung auslösen
- Die Statusbögen zeigen WiFi (links) und Hub-Verbindung (rechts)

## Telemetrie-Payload

```json
{
  "deviceId": "m5stack-cores3",
  "seq": 42,
  "timestamp": 1715152800,
  "temperature": 23.45,
  "humidity": 48.12,
  "pressure": 1013.25,
  "gasResistance": 15000,
  "heatStable": true
}
```

## Projektstruktur

| Datei | Beschreibung | Gerät |
|-------|--------------|-------|
| `cores3.py` | Hauptanwendung für CoreS3 (Touch, rechteckiges Display) | CoreS3 |
| `dial.py` | Hauptanwendung für DIAL v1.1 (Encoder, rundes Display) | DIAL v1.1 |

## Features

### Allgemein
- **Visuelles Dashboard** auf dem Display
- **Statusanzeige** für WiFi- und IoT Hub-Verbindung
- **Automatische Wiederverbindung** bei Verbindungsverlust
- **Vollständiger BME688-Treiber** in Python implementiert
- **Fehlerbehandlung** mit Retry-Logik

### CoreS3
- 3 Sensor-Karten gleichzeitig sichtbar
- Touch-Interface (bereit für Erweiterungen)

### DIAL v1.1
- Interaktive Sensor-Auswahl per Encoder
- Farbiger Akzentring für aktiven Sensor
- Sofortige Messung per Tastendruck
- Zweigeteilter Statusbogen (WiFi/Hub) am Außenring

## Lizenz

Dies ist ein Demo-Projekt für Bildungszwecke – Prof. Dr. Suat Can, HsH BDT-Demo.
