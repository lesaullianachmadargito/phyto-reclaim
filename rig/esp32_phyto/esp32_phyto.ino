/*
 * PHYTO-RECLAIM - Module III bench sensor node
 * Board: ESP32-S3 DevKitC
 *
 * WHAT THIS NODE DOES
 *   Reads TDS, pH and temperature from a single beaker, publishes them over
 *   MQTT, and receives valve commands from the stage-gate logic in Node-RED.
 *
 * WHY IT MATTERS FOR THE COMPETITION
 *   This node MEASURES the detection-to-diversion time that the paper admits
 *   has never been measured. Every interval is measured on one and the same
 *   clock (the ESP32's own micros()), so no cross-device time synchronisation
 *   is required - measuring the gap between two unsynchronised clocks would
 *   produce a meaningless number.
 *
 *   The chain is broken down exactly as the paper names it:
 *     1. t_sampling   - interval between sensor reads (known constant)
 *     2. t_transport  - liquid travel time in the pipe (N/A at beaker scale)
 *     3. t_logic      - sample read until the command arrives (network + logic)
 *     4. t_valve      - command received until the limit switch closes
 *
 * THE CAVEAT THAT MUST STILL BE SAID OUT LOUD
 *   The ESP32-S3 is a laboratory prototype platform. It is NOT certified for
 *   hazardous areas and will never be installed in the field. The paper already
 *   states this; do not let the demo suggest otherwise.
 *
 * LIBRARIES (Arduino IDE Library Manager)
 *   PubSubClient          - Nick O'Leary
 *   OneWire               - Paul Stoffregen
 *   DallasTemperature     - Miles Burton
 *   ESP32Servo            - Kevin Harrington
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <ESP32Servo.h>

// ----------------------------------------------------------------- network
const char* WIFI_SSID = "YOUR_WIFI_NAME";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
const char* MQTT_HOST = "192.168.1.10";   // IP of the laptop running Node-RED
const uint16_t MQTT_PORT = 1883;

const char* TOPIC_TELEMETRY = "phyto/telemetry";
const char* TOPIC_COMMAND   = "phyto/cmd";
const char* TOPIC_LATENCY   = "phyto/latency";

// ----------------------------------------------------------------- pins (ESP32-S3)
// Note: the ESP32-S3 uses GPIO1..GPIO10 for ADC1. On a classic ESP32, move the
// analog pins to GPIO34/35 and adjust the rest.
const int PIN_TDS   = 4;    // ADC1
const int PIN_PH    = 5;    // ADC1
const int PIN_TEMP  = 6;    // OneWire DS18B20
const int PIN_SERVO = 7;    // servo standing in for the valve
const int PIN_LIMIT = 15;   // limit switch, INPUT_PULLUP, LOW = valve closed
const int PIN_LED   = 2;    // status indicator

// ----------------------------------------------------------------- parameters
const uint32_t SAMPLE_MS = 500;      // interval between sensor reads = link 1
const int SERVO_OPEN = 90;
const int SERVO_CLOSED = 0;
const uint32_t LIMIT_TIMEOUT_MS = 3000;

// Two-point pH calibration. Replace with your own buffer 4.00 and 7.00 readings.
const float PH_V4 = 2.030;   // volts read in pH 4.00 buffer
const float PH_V7 = 1.500;   // volts read in pH 7.00 buffer

// ----------------------------------------------------------------- objects
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
OneWire oneWire(PIN_TEMP);
DallasTemperature tempSensor(&oneWire);
Servo valve;

uint32_t seq = 0;
uint32_t lastSample = 0;
bool valveOpen = true;

// Ring buffer of sample timestamps, so an arriving command can be matched back
// to the sensor reading that triggered it.
const int RING = 32;
uint32_t ringSeq[RING];
uint32_t ringUs[RING];
int ringIdx = 0;

void storeSampleTime(uint32_t s, uint32_t us) {
  ringSeq[ringIdx] = s;
  ringUs[ringIdx] = us;
  ringIdx = (ringIdx + 1) % RING;
}

bool lookupSampleTime(uint32_t s, uint32_t* us) {
  for (int i = 0; i < RING; i++) {
    if (ringSeq[i] == s) { *us = ringUs[i]; return true; }
  }
  return false;
}

// ----------------------------------------------------------------- sensors
float readVoltage(int pin) {
  uint32_t total = 0;
  for (int i = 0; i < 16; i++) { total += analogRead(pin); delayMicroseconds(200); }
  return (total / 16.0f) * 3.3f / 4095.0f;
}

float readTDS(float tempC) {
  float v = readVoltage(PIN_TDS);
  // Standard Gravity TDS sensor temperature compensation
  float coef = 1.0f + 0.02f * (tempC - 25.0f);
  float vk = v / coef;
  return (133.42f * vk * vk * vk - 255.86f * vk * vk + 857.39f * vk) * 0.5f;
}

float readPH() {
  float v = readVoltage(PIN_PH);
  float slope = (7.0f - 4.0f) / (PH_V7 - PH_V4);   // pH per volt
  return 7.0f + (v - PH_V7) * slope;
}

// ----------------------------------------------------------------- valve
// Returns valve travel time in microseconds, measured until the limit switch
// reacts. With no limit switch fitted the figure is the time until timeout -
// and that MUST be reported as an estimate, not a measurement.
uint32_t driveValve(bool open) {
  uint32_t t0 = micros();
  valve.write(open ? SERVO_OPEN : SERVO_CLOSED);
  digitalWrite(PIN_LED, open ? LOW : HIGH);

  uint32_t deadline = millis() + LIMIT_TIMEOUT_MS;
  while (millis() < deadline) {
    bool closed = (digitalRead(PIN_LIMIT) == LOW);
    if (closed != open) break;        // position reached
    delayMicroseconds(200);
  }
  valveOpen = open;
  return micros() - t0;
}

// ----------------------------------------------------------------- MQTT
void onMessage(char* topic, byte* payload, unsigned int len) {
  uint32_t tCmd = micros();           // recorded BEFORE anything else

  char buf[192];
  unsigned int n = len < sizeof(buf) - 1 ? len : sizeof(buf) - 1;
  memcpy(buf, payload, n);
  buf[n] = '\0';

  // The payload is deliberately simple so no JSON library is needed:
  //   {"seq":123,"action":"CLOSE"}
  uint32_t sAck = 0;
  char* pSeq = strstr(buf, "\"seq\":");
  if (pSeq) sAck = strtoul(pSeq + 6, NULL, 10);
  bool wantClosed = (strstr(buf, "CLOSE") != NULL);

  if (wantClosed == !valveOpen) return;        // already in that position

  uint32_t valveTravel = driveValve(!wantClosed);

  uint32_t tSample = 0;
  bool matched = lookupSampleTime(sAck, &tSample);
  uint32_t tLogic = matched ? (tCmd - tSample) : 0;
  uint32_t tTotal = matched ? (micros() - tSample) : 0;

  char out[256];
  snprintf(out, sizeof(out),
           "{\"seq\":%lu,\"matched\":%s,"
           "\"t_sampling_us\":%lu,\"t_logic_us\":%lu,"
           "\"t_valve_us\":%lu,\"t_total_us\":%lu,"
           "\"action\":\"%s\"}",
           (unsigned long)sAck, matched ? "true" : "false",
           (unsigned long)(SAMPLE_MS * 1000UL),
           (unsigned long)tLogic, (unsigned long)valveTravel,
           (unsigned long)tTotal, wantClosed ? "CLOSE" : "OPEN");
  mqtt.publish(TOPIC_LATENCY, out);
}

void connectMqtt() {
  while (!mqtt.connected()) {
    String id = "phyto-esp32-" + String((uint32_t)ESP.getEfuseMac(), HEX);
    if (mqtt.connect(id.c_str())) {
      mqtt.subscribe(TOPIC_COMMAND);
      Serial.println("MQTT connected");
    } else {
      Serial.print("MQTT failed, rc="); Serial.println(mqtt.state());
      delay(2000);
    }
  }
}

// ----------------------------------------------------------------- setup
void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_LIMIT, INPUT_PULLUP);
  analogReadResolution(12);

  tempSensor.begin();
  valve.attach(PIN_SERVO);
  valve.write(SERVO_OPEN);

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(400); Serial.print("."); }
  Serial.println();
  Serial.print("IP: "); Serial.println(WiFi.localIP());

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
  connectMqtt();
}

// ----------------------------------------------------------------- loop
void loop() {
  if (!mqtt.connected()) connectMqtt();
  mqtt.loop();

  if (millis() - lastSample < SAMPLE_MS) return;
  lastSample = millis();

  tempSensor.requestTemperatures();
  float temp = tempSensor.getTempCByIndex(0);
  if (temp < -100) temp = 25.0f;               // sensor detached, use a safe value

  uint32_t tSample = micros();                 // link 1 starts here
  float tds = readTDS(temp);
  float ph = readPH();

  seq++;
  storeSampleTime(seq, tSample);

  char out[256];
  snprintf(out, sizeof(out),
           "{\"seq\":%lu,\"t_sample_us\":%lu,\"tds\":%.1f,\"ph\":%.2f,"
           "\"temp\":%.2f,\"valve\":\"%s\"}",
           (unsigned long)seq, (unsigned long)tSample,
           tds, ph, temp, valveOpen ? "OPEN" : "CLOSED");
  mqtt.publish(TOPIC_TELEMETRY, out);
}
