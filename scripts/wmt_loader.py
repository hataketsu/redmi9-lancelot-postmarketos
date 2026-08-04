#!/usr/bin/env python3
"""Thay cho `wmt_loader` cua Android: danh thuc chip connectivity MT6768.

Binary vendor la bionic nen khong chay tren musl. Chuoi ioctl thi don gian, chep lai
tu drivers/misc/mediatek/connectivity/common/common_detect/wmt_detect.{c,h}:

    WMT_DETECT_IOC_MAGIC = 'w' (0x77)
    _IOR(magic, nr, int) = (2 << 30) | (4 << 16) | (magic << 8) | nr
    _IOW(magic, nr, int) = (1 << 30) | (4 << 16) | (magic << 8) | nr

ioctl tra ket qua qua gia tri tra ve, khong qua con tro.
"""
import fcntl
import os
import sys


def _ior(magic, nr):
    return (2 << 30) | (4 << 16) | (magic << 8) | nr


def _iow(magic, nr):
    return (1 << 30) | (4 << 16) | (magic << 8) | nr


M = 0x77
GET_CHIP_ID     = _ior(M, 0)
SET_CHIP_ID     = _iow(M, 1)
GET_SOC_CHIP_ID = _ior(M, 3)
DO_MODULE_INIT  = _ior(M, 4)


def signed(req):
    """fcntl.ioctl muon so vua trong c_int."""
    return req - (1 << 32) if req >= (1 << 31) else req


def call(fd, req, arg=0, name=""):
    try:
        r = fcntl.ioctl(fd, signed(req), arg)
        print(f"  {name:16} -> {r} ({r:#x})" if isinstance(r, int) else f"  {name:16} -> {r}")
        return r
    except Exception as exc:
        print(f"  {name:16} !! {exc}")
        return None


def main():
    dev = "/dev/wmtdetect"
    if not os.path.exists(dev):
        sys.exit(f"{dev} khong ton tai")
    fd = os.open(dev, os.O_RDWR)
    print(f"mo {dev}")

    chip = call(fd, GET_CHIP_ID, 0, "GET_CHIP_ID")
    if chip is None or chip <= 0:
        chip = call(fd, GET_SOC_CHIP_ID, 0, "GET_SOC_CHIP_ID")
    if chip is None or chip <= 0:
        print("khong doc duoc chip id, thu 0x6768")
        chip = 0x6768

    print(f"chip id = {chip:#x}")
    call(fd, SET_CHIP_ID, chip, "SET_CHIP_ID")
    call(fd, DO_MODULE_INIT, chip, "DO_MODULE_INIT")
    os.close(fd)

    print("--- /dev sau khi init ---")
    print(" ".join(sorted(d for d in os.listdir("/dev")
                          if any(k in d.lower() for k in ("wmt", "stp", "conn", "wifi")))))


if __name__ == "__main__":
    main()
