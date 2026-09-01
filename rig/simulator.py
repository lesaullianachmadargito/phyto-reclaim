# -*- coding: utf-8 -*-
"""Stand-in for the ESP32 so the dashboard can be built before sensors arrive.

This script speaks exactly like the `esp32_phyto.ino` firmware: same topics,
same payload shape, same latency reporting. So you can finish the whole Node-RED
flow today, then simply stop the simulator and switch on the ESP32 without
changing anything on the Node-RED side.

What is simulated: a beaker of water. Every few seconds a "salt pour" pushes TDS
past the 4,000 mg/L threshold — mimicking what you will do in front of the
judges.

    python simulator.py                     # broker on localhost
    python simulator.py --host 192.168.1.5  # broker elsewhere

Stop with Ctrl+C.
"""
import argparse
import json
import math
import random
import sys
import time

import paho.mqtt.client as mqtt

TOPIC_TELEMETRY = "phyto/telemetry"
TOPIC_COMMAND = "phyto/cmd"
TOPIC_LATENCY = "phyto/latency"

SAMPLE_MS = 500          # matches SAMPLE_MS in the firmware
VALVE_TRAVEL_MS = 1200   # the 1.2 s valve actuation target quoted in the paper


class Beaker:
    """A very small beaker model — just enough to exercise the dashboard."""

    def __init__(self):
        self.tds = 1800.0        # mg/L, starting water
        self.ph = 7.4
        self.temp = 29.5
        self.valve_open = True
        self.t0 = time.time()

    def step(self, dt):
        # TDS decays slowly back toward baseline as water is topped up
        self.tds += (1800.0 - self.tds) * 0.02 * dt
        self.tds += random.gauss(0, 6)
        # pH and temperature drift within a plausible band
        t = time.time() - self.t0
        self.ph = 7.4 + 0.25 * math.sin(t / 40) + random.gauss(0, 0.02)
        self.temp = 29.5 + 1.2 * math.sin(t / 90) + random.gauss(0, 0.05)

    def pour_salt(self, mg_per_l=3200.0):
        self.tds += mg_per_l


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost", help="MQTT broker address")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--every", type=float, default=25.0,
                    help="seconds between automatic salt pours")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    beaker = Beaker()
    seq = {"n": 0}
    sample_time = {}          # seq -> monotonic time the sensor was read

    def on_connect(client, userdata, flags, reason_code, properties=None):
        print(f"connected to broker {args.host}:{args.port} (rc={reason_code})")
        client.subscribe(TOPIC_COMMAND)

    def on_message(client, userdata, msg):
        # Command time is recorded BEFORE anything else, same as the firmware.
        t_cmd = time.perf_counter()
        try:
            data = json.loads(msg.payload.decode())
        except Exception:
            return
        s_ack = int(data.get("seq", 0))
        close = str(data.get("action", "")).upper() == "CLOSE"
        if close == (not beaker.valve_open):
            return                                   # already in that position

        time.sleep(VALVE_TRAVEL_MS / 1000.0)         # the valve travels
        t_valve = time.perf_counter()
        beaker.valve_open = not close

        t_sample = sample_time.get(s_ack)
        matched = t_sample is not None
        t_logic = (t_cmd - t_sample) if matched else 0.0
        t_total = (t_valve - t_sample) if matched else 0.0

        report = {
            "seq": s_ack,
            "matched": matched,
            "t_sampling_us": int(SAMPLE_MS * 1000),
            "t_logic_us": int(t_logic * 1e6),
            "t_valve_us": int((t_valve - t_cmd) * 1e6),
            "t_total_us": int(t_total * 1e6),
            "action": "CLOSE" if close else "OPEN",
        }
        client.publish(TOPIC_LATENCY, json.dumps(report))
        print(f"  command {report['action']:5} seq={s_ack:<5} "
              f"logic {t_logic * 1000:6.1f} ms · "
              f"valve {(t_valve - t_cmd) * 1000:6.1f} ms · "
              f"total {t_total * 1000:6.1f} ms")

    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    cli.on_connect = on_connect
    cli.on_message = on_message
    cli.connect(args.host, args.port, 60)
    cli.loop_start()

    print("PHYTO-RECLAIM beaker simulator running. Ctrl+C to stop.")
    print(f"Automatic salt pour every {args.every:.0f} seconds.\n")

    dt = SAMPLE_MS / 1000.0
    next_pour = time.time() + args.every
    try:
        while True:
            beaker.step(dt)
            if time.time() >= next_pour:
                beaker.pour_salt()
                next_pour = time.time() + args.every
                print(f"  >> salt poured, TDS rises to {beaker.tds:.0f} mg/L")

            seq["n"] += 1
            k = seq["n"]
            sample_time[k] = time.perf_counter()
            if len(sample_time) > 200:
                sample_time.pop(min(sample_time))

            message = {
                "seq": k,
                "t_sample_us": int(sample_time[k] * 1e6),
                "tds": round(beaker.tds, 1),
                "ph": round(beaker.ph, 2),
                "temp": round(beaker.temp, 2),
                "valve": "OPEN" if beaker.valve_open else "CLOSED",
            }
            cli.publish(TOPIC_TELEMETRY, json.dumps(message))
            time.sleep(dt)
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        cli.loop_stop()
        cli.disconnect()


if __name__ == "__main__":
    main()
