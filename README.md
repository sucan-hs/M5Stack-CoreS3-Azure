# M5Stack CoreS3 + BME688 → Azure IoT Hub

MicroPython-Anwendung für den **M5Stack CoreS3** mit **EnV Pro Unit (BME688-Sensor)** zur Erfassung von Umweltdaten und Übertragung an **Azure IoT Hub**.

## Überblick

Dieses Projekt liest Temperatur, Luftfeuchtigkeit, Luftdruck und Gaswiderstand vom BME688-Sensor und sendet die Daten per MQTT an Azure IoT Hub. Die Messwerte werden auf dem 320x240 Display des CoreS3 in Echtzeit angezeigt.

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

## Hardware

| Komponente | Beschreibung | Verbindung |
|------------|--------------|------------|
| M5Stack CoreS3 | ESP32-S3 Entwicklungsboard mit 320x240 Display | - |
| EnV Pro Unit | BME688 Sensor (Temp, Feuchte, Druck, Gas) | I2C (GPIO 1/2) |

**I2C-Pins:**
- SDA: GPIO 2
- SCL: GPIO 1
- Adresse: 0x77

## Software-Voraussetzungen

- [UIFlow2](https://uiflow2.m5stack.com/) oder MicroPython für CoreS3
- `umqtt.simple` Bibliothek (in UIFlow2 enthalten)

## Konfiguration

Bearbeiten Sie die Konfigurationsvariablen in `main.py`:

```python
# WLAN
WIFI_SSID       = "DEIN_WLAN_SSID"
WIFI_PASSWORD   = "DEIN_WLAN_PASSWORT"

# Azure IoT Hub
IOT_HUB_HOST    = "DEIN-HUB.azure-devices.net"
DEVICE_ID       = "m5stack-cores3"
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

1. Flashen Sie `main.py` auf den CoreS3 (z.B. mit [M5Burner](https://docs.m5stack.com/en/download))
2. Das Gerät verbindet sich automatisch mit WLAN und Azure IoT Hub
3. Sensorwerte werden alle 30 Sekunden gesendet
4. Nachrichten vom IoT Hub werden in der Konsole ausgegeben

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

| Datei | Beschreibung |
|-------|--------------|
| `main.py` | Hauptanwendung mit Display-UI, BME688-Treiber, MQTT-Client |

## Features

- **Visuelles Dashboard** mit 3 Sensor-Karten auf dem Display
- **Statusanzeige** für WiFi- und IoT Hub-Verbindung
- **Automatische Wiederverbindung** bei Verbindungsverlust
- **Vollständiger BME688-Treiber** in Python implementiert
- **Fehlerbehandlung** mit Retry-Logik

## Lizenz

Dies ist ein Demo-Projekt für Bildungszwecke – Prof. Dr. Suat Can, HsH BDT-Demo.
