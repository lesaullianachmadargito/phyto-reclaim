# Module III bench rig — ESP32 + Node-RED

A small rig that turns one beaker of water into evidence you can show: sensors
read TDS, stage-gate logic closes the valve when TDS crosses the 4,000 mg/L
envelope, and the **detection-to-diversion time is actually measured** — the
figure your paper admits has never been measured.

Folder contents:

| File | Purpose |
|---|---|
| `esp32_phyto/esp32_phyto.ino` | Sensor node firmware. |
| `flow_nodered.json` | Node-RED flow: local broker, dashboard, stage-gate logic, latency measurement. |
| `simulator.py` | Stand-in for the ESP32, so the dashboard can be built before sensors arrive. |

---

## Start today, without waiting for hardware

Everything below is already installed and has been tested working on this laptop.

**1. Run Node-RED with the flow:**

```
cd C:\Users\HP\Downloads\phyto-twin\rig
node-red --userDir .\_nrdata --port 1880
```

On this laptop the flow is already copied to `_nrdata\flows.json`. On a fresh
clone that folder does not exist yet — it is git-ignored — so create it first:

```
mkdir _nrdata
copy flow_nodered.json _nrdata\flows.json
```

Or start Node-RED and use **Menu → Import → select `flow_nodered.json`**.

The `aedes` node inside the flow starts a local MQTT broker on port 1883, so the
rig needs **no internet** — which matters, because venue WiFi cannot be relied
on.

**2. In a second terminal, run the beaker simulator:**

```
python -u simulator.py --every 12
```

**3. Open the dashboard:** `http://localhost:1880/ui/`
Flow editor: `http://localhost:1880/`

What you should see: three gauges filling, a TDS trend that jumps each time the
simulator "pours salt", **PBR SIDE-STREAM CLOSED** appearing once TDS passes
4,000, and the latency chain table filling with measured numbers.

The simulator uses exactly the same topics and payload shape as the firmware, so
later you just stop the simulator and switch on the ESP32 — nothing on the
Node-RED side changes.

---

## Shopping list

Approximate Tokopedia prices, September 2026.

| Component | Approx. |
|---|---|
| ESP32-S3 DevKitC-1 | IDR 90,000 – 150,000 |
| Analog TDS sensor (Gravity type) | IDR 120,000 – 180,000 |
| Analog pH sensor PH4502C + E-201-C probe | IDR 180,000 – 350,000 |
| DS18B20 waterproof probe | IDR 20,000 – 35,000 |
| SG90 servo (valve stand-in) | IDR 15,000 – 25,000 |
| Micro limit switch | IDR 5,000 |
| 4.7 kΩ resistor (DS18B20 pull-up) | IDR 1,000 |
| Breadboard + jumper wires | IDR 30,000 |
| **Total** | **± IDR 460,000 – 780,000** |

On a tight budget the pH sensor can be skipped. TDS, temperature, servo and
limit switch already cover the entire demo — pH only adds completeness.

---

## Wiring

Pins below are for the **ESP32-S3**. On a classic ESP32 the analog pins differ
(use GPIO34/35) — adjust the constants at the top of the firmware.

| Component | ESP32-S3 pin | Note |
|---|---|---|
| TDS sensor (AOUT) | GPIO4 | ADC1 |
| pH sensor (Po) | GPIO5 | ADC1 |
| DS18B20 (data) | GPIO6 | 4.7 kΩ pull-up to 3V3 |
| Servo (signal) | GPIO7 | power the servo from 5V, **not** 3V3 |
| Limit switch | GPIO15 | to GND, `INPUT_PULLUP`; LOW = valve closed |
| Status LED | GPIO2 | |

Servo ground and ESP32 ground **must be tied together**, otherwise the signal
misbehaves.

Before uploading, change four things at the top of `esp32_phyto.ino`:
`WIFI_SSID`, `WIFI_PASS`, `MQTT_HOST` (the IP of the laptop running Node-RED —
find it with `ipconfig`), and the pH calibration `PH_V4` / `PH_V7`.

Libraries to install through the Arduino IDE Library Manager: PubSubClient,
OneWire, DallasTemperature, ESP32Servo.

---

## Measuring detection-to-diversion time

This is the main reason the rig exists.

### Why it is designed this way

Every interval is measured on **one and the same clock** — the ESP32's own
`micros()`. Measuring the gap between the ESP32 clock and the laptop clock would
produce a meaningless number, because the two are not synchronised. So the node
records the sample time, the node records when the valve closes, and the node
computes the difference.

### The chain it reports

Exactly the four links the paper names:

| Link | How it is obtained |
|---|---|
| 1. Sensor sampling | The `SAMPLE_MS` constant in the firmware (500 ms by default) |
| 2. Transport lag | **N/A at beaker scale** — there is no pipe. Do not invent a number |
| 3. Network + logic | Time from sample read until the command arrives at the node |
| 4. Valve travel | Command received until the limit switch reacts |

Link 2 is deliberately left empty. That shows you understand what has *not* been
measured — and in a real field installation, transport lag in the pipe is
usually the largest link of the four.

### The protocol

1. Fill the beaker with water below 3,000 mg/L TDS. Let the reading settle.
2. Pour salt until TDS passes 4,000 mg/L.
3. Record the "Total measured" row from the dashboard.
4. Rinse and repeat. **Do at least 20 runs.**
5. Report the **median and the range**, never the best run. Quoting the best of
   20 attempts is the easiest form of overstatement for a judge to catch.

An honest way to state the result:

> "On the bench rig, the median detection-to-diversion time over 20 runs was
> 1.21 s (range 1.19–1.28), with valve travel dominating at 1.20 s and network
> plus logic under 10 ms. Transport lag was not measured because there is no
> pipe at this scale — that is one of the things Phase 1 has to measure."

---

## What this rig proves, and what it does not

**It proves:**
- The stage-gate chain works end to end: sensor → logic → actuator.
- Response time can be measured, and the per-link breakdown is sensible.
- The proposed SCADA architecture can be built, not merely drawn.

**It does not prove:**
- Performance on real produced water. This is a beaker of salty water.
- Hazardous-area suitability. The ESP32-S3 is a laboratory prototype platform,
  **not certified**, and will never be installed in the field. The paper already
  says so — do not let the demo suggest otherwise.
- Field response time. There is no pipe transport lag here.

A safe sentence to say yourself, before a judge asks:

> "This is a bench rig on a prototype platform. What we demonstrate is that the
> control chain functions and its timing can be measured. Field hardware would
> have to be a hazardous-area certified controller, and the numbers would have
> to be measured again there."

---

## Only once this rig runs may the phrase "digital twin" be used

With real sensors mirroring a real physical object in real time, there genuinely
is a synchronised physical asset — even if it is only a beaker. At that scale
the term is legitimate. Use it in full: **"bench-scale digital twin"**, never
"digital twin" unqualified.

Before this rig exists, what you have is a process simulation model — and
`app.py` in the parent folder deliberately describes itself that way.
