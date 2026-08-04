#!/usr/bin/env python3
"""Ghi lien tuc su kien tu /dev/input/eventN ra /tmp/touchlog.txt.

struct input_event tren arm64 dai 24 byte (timeval 16 + type 2 + code 2 + value 4).
Doc it hon 24 byte thi kernel tu choi read() ngay -- de nham thanh "khong co su kien".
"""
import struct, sys, time, traceback

EVSZ = 24
EV  = {0: "SYN", 1: "KEY", 3: "ABS"}
ABS = {0x00: "X", 0x01: "Y", 0x18: "PRESSURE",
       0x2f: "MT_SLOT", 0x30: "MT_TOUCH_MAJOR", 0x35: "MT_POS_X",
       0x36: "MT_POS_Y", 0x39: "MT_TRACKING_ID", 0x3a: "MT_PRESSURE"}
KEY = {0x14a: "BTN_TOUCH"}

dev = sys.argv[1] if len(sys.argv) > 1 else "/dev/input/event2"
out = open("/tmp/touchlog.txt", "a", buffering=1)
out.write(f"--- mo {dev} luc {time.time():.0f} (event size {EVSZ}) ---\n")

try:
    with open(dev, "rb", buffering=0) as f:
        while True:
            b = f.read(EVSZ)
            if not b or len(b) < EVSZ:
                out.write(f"--- read tra ve {0 if not b else len(b)} byte, dung ---\n")
                break
            _, _, t, c, v = struct.unpack("qqHHi", b)
            name = KEY.get(c, hex(c)) if t == 1 else ABS.get(c, hex(c)) if t == 3 else hex(c)
            out.write(f"{EV.get(t, t)} {name} {v}\n")
except Exception:
    out.write("--- ngoai le ---\n" + traceback.format_exc())
