#!/usr/bin/env python3
"""Thay cho `wmt_launcher` cua Android tren pmOS.

Khi bat WiFi, kernel khong tu tim file ROM patch. No dat mot chuoi lenh vao
/dev/stpwmt roi cho 6 giay:

    wmt_ctrl_ul_cmd()  ->  cCmd = "srh_rom_patch",  cho tin hieu
    userspace          ->  read("/dev/stpwmt") lay chuoi lenh
                           ioctl(SET_ROM_PATCH_INFO) cho tung loai
                           write("ok")

Khong co ai tra loi thi:
    wmt_ctrl_ul_cmd(468): wait signal timeout
    mtk_wcn_soc_rom_patch_dwn(3532): failed to get patch (type: 0, ret: -1)
    [MTK-WIFI] WIFI_write[E]: WMT turn on WIFI fail!

Header file patch la `struct wmt_rom_patch` (wmt_core.h):
    [0:16]  ucDateTime      [16:20] ucPLat = "ALPS"
    [20:22] u2HwVer         [22:24] u2SwVer
    [24:28] u4PatchAddr     [28:32] u4PatchType
Kernel tinh vi tri trong EMI bang
    patchEmiOffset = a[2] << 16 | a[1] << 8 | a[0]
va `u4PatchAddr & 0x00FFFF00` cho ra dung bo cuc chuan cua MTK:
    mcu 0x000000, bt 0x080000, wifi 0x140000
"""
import ctypes
import fcntl
import re
import subprocess
import os
import struct
import sys
import time

FW_DIR = "/lib/firmware"
DEV = "/dev/stpwmt"

WMT_IOC_MAGIC = 0xA0


def _iow(magic, nr, size):
    return (1 << 30) | (size << 16) | (magic << 8) | nr


# _IOW(WMT_IOC_MAGIC, 31, char*) -- con tro 8 byte tren arm64
WMT_IOCTL_SET_ROM_PATCH_INFO = _iow(WMT_IOC_MAGIC, 31, 8)
# _IOW(WMT_IOC_MAGIC, 5, int) -- arg truyen thang, khong phai con tro
WMT_IOCTL_SET_STP_MODE = _iow(WMT_IOC_MAGIC, 5, 4)
WMT_IOCTL_SET_PATCH_NUM = _iow(WMT_IOC_MAGIC, 14, 4)
WMT_IOCTL_SET_PATCH_INFO = _iow(WMT_IOC_MAGIC, 15, 8)

# wmt_lib_set_hif() giai ma tham so nhu sau:
#   bit [3:0] kieu giao dien STP,  bit [7:4] che do FM
# MT6768 chay STP tren BTIF. Khong goi ioctl nay thi wmt_core_stp_init() bao
# "no hif info!" va bat WiFi that bai.
STP_BTIF_FULL = 0x03
WMT_FM_COMM = 2
HIF_CONF = STP_BTIF_FULL | (WMT_FM_COMM << 4)

# Chi ba loai nay co ROM patch; xem enum ENUM_WMTDRV_TYPE_T.
TYPE_NAME = {0: "BT", 3: "WIFI", 4: "WMT/mcu"}


def signed(req):
    return req - (1 << 32) if req >= (1 << 31) else req


def chip_hw_ver():
    """Doc phien ban HW cua CONSYS tu dmesg: 'consys HW version id(0x8a00)'.

    Trong file patch, u2HwVer luu dao byte so voi cach kernel in ra, nen 0x8a00
    tuong ung 0x008a.
    """
    try:
        out = subprocess.run(["dmesg"], capture_output=True, text=True).stdout
    except OSError:
        return None
    m = None
    for m in re.finditer(r"consys HW version id\((0x[0-9a-fA-F]+)\)", out):
        pass
    if not m:
        return None
    printed = int(m.group(1), 16)
    return ((printed & 0xFF) << 8) | (printed >> 8)


def soc_prefix():
    """Ho chip lay tu ten file WIFI_RAM_CODE_<prefix>_*.bin, vd 'soc1_0'."""
    for name in os.listdir(FW_DIR):
        m = re.match(r"WIFI_RAM_CODE_(soc\d+_\d+)_", name)
        if m:
            return m.group(1)
    return None


def scan_patches():
    """Tra ve {type: (ten file, emi_offset)} tu cac file co header ALPS.

    Thu muc firmware chua ca hai ho chip. Chon sai la kernel van nap duoc vao EMI
    nhung chip khong chay: soc3_0_ram_mcu_*.bin co HwVer 0x8a10 trong khi chip nay
    bao 0x8a00. Loc theo ca ho chip lan HwVer.
    """
    want_hw = chip_hw_ver()
    prefix = soc_prefix()
    print(f"ho chip: {prefix}   HwVer mong doi: "
          f"{want_hw:#06x}" if want_hw else f"ho chip: {prefix}   HwVer: khong doc duoc",
          flush=True)

    found = {}
    for name in sorted(os.listdir(FW_DIR)):
        if prefix and not name.startswith(prefix + "_"):
            continue
        path = os.path.join(FW_DIR, name)
        try:
            with open(path, "rb") as f:
                hdr = f.read(32)
        except OSError:
            continue
        if len(hdr) < 32 or hdr[16:20] != b"ALPS":
            continue
        hw_ver, = struct.unpack_from("<H", hdr, 20)
        if want_hw is not None and hw_ver != want_hw:
            print(f"  bo qua {name}: HwVer {hw_ver:#06x}", flush=True)
            continue
        patch_addr, = struct.unpack_from("<I", hdr, 24)
        patch_addr &= 0xFFFFFF00   # bo byte thap 0x11, xem chu thich o find_mcu_patch
        ptype = hdr[31]            # u4PatchType luu kieu big-endian trong file
        if ptype not in TYPE_NAME:
            continue               # vd soc1_0_patch_mcu_*: di duong tai khac
        found[ptype] = (name, patch_addr & 0x00FFFFFF)
    return found


def find_mcu_patch(prefix):
    """File ROM patch co dien: <prefix>_patch_mcu_*_hdr.bin.

    Khac cac file ram_*: u4PatchType khong phai ma loai (0xFF...), va dia chi
    duoc gui thang trong lenh WMT chu khong dung lam offset EMI.
    """
    for name in sorted(os.listdir(FW_DIR)):
        if not (name.startswith(f"{prefix}_patch_mcu") and name.endswith("_hdr.bin")):
            continue
        with open(os.path.join(FW_DIR, name), "rb") as f:
            hdr = f.read(32)
        if len(hdr) >= 32 and hdr[16:20] == b"ALPS":
            patch_addr, = struct.unpack_from("<I", hdr, 24)
            # Byte thap luon la 0x11 trong moi file patch cua chip nay; bo di moi
            # ra dia chi thang hang (0x0001c000, 0xf0000000, 0xf0080000, 0xf0140000).
            # Giu nguyen 0x11 thi chip nap xong la treo, khong tra loi "wmt reset".
            return name, struct.pack("<I", patch_addr & 0xFFFFFF00)
    return None, None


def set_patch_info(fd, seq, name, addr_bytes):
    # struct WMT_PATCH_INFO { UINT32 dowloadSeq; UINT8 addRess[4]; UINT8 patchName[256]; }
    buf = ctypes.create_string_buffer(
        struct.pack("<I", seq) + bytes(addr_bytes) + name.encode().ljust(256, b"\0"),
        264)
    fcntl.ioctl(fd, signed(WMT_IOCTL_SET_PATCH_INFO), buf)


def set_rom_patch_info(fd, ptype, name, emi_off):
    # struct wmt_rom_patch_info { UINT32 type; UINT8 addRess[4]; UINT8 patchName[256]; }
    buf = ctypes.create_string_buffer(
        struct.pack("<I", ptype)
        + struct.pack("<I", emi_off)          # a[0]=LSB, khop cach kernel ghep lai
        + name.encode().ljust(256, b"\0"),
        264)
    fcntl.ioctl(fd, signed(WMT_IOCTL_SET_ROM_PATCH_INFO), buf)


def handle(fd, cmd, patches):
    if cmd.startswith("srh_rom_patch"):
        if not patches:
            print("  khong tim thay file ROM patch nao", flush=True)
            return False
        for ptype, (name, emi_off) in sorted(patches.items()):
            set_rom_patch_info(fd, ptype, name, emi_off)
            print(f"  dang ky type {ptype} ({TYPE_NAME[ptype]}): "
                  f"{name} @ EMI +{emi_off:#08x}", flush=True)
        return True
    if cmd.startswith("srh_patch"):
        name, addr = find_mcu_patch(soc_prefix() or "")
        if not name:
            print("  khong tim thay file patch_mcu", flush=True)
            return False
        fcntl.ioctl(fd, signed(WMT_IOCTL_SET_PATCH_NUM), 1)
        set_patch_info(fd, 1, name, addr)
        print(f"  dang ky patch MCU: {name} addr={addr.hex()}", flush=True)
        return True

    # Cac lenh khac chua can lam gi; bao ok de kernel di tiep.
    print(f"  lenh chua xu ly: {cmd!r}, tra ok", flush=True)
    return True


def main():
    patches = scan_patches()
    print("ROM patch tim thay:", flush=True)
    for t, (n, o) in sorted(patches.items()):
        print(f"  type {t} ({TYPE_NAME[t]}): {n} @ EMI +{o:#08x}", flush=True)
    if not patches:
        sys.exit(f"khong thay file patch nao trong {FW_DIR}")

    fd = os.open(DEV, os.O_RDWR)

    try:
        fcntl.ioctl(fd, signed(WMT_IOCTL_SET_STP_MODE), HIF_CONF)
        print(f"SET_STP_MODE {HIF_CONF:#04x} (BTIF full + FM comm) OK", flush=True)
    except Exception as exc:
        print(f"SET_STP_MODE that bai: {exc}", flush=True)

    print(f"dang nghe {DEV}", flush=True)
    try:
        while True:
            try:
                data = os.read(fd, 256)
            except OSError as exc:
                print("read loi:", exc, flush=True)
                time.sleep(0.1)
                continue
            if not data:
                time.sleep(0.02)
                continue
            cmd = data.decode(errors="replace").strip("\0").strip()
            print(f"lenh: {cmd!r}", flush=True)
            ok = handle(fd, cmd, patches)
            os.write(fd, b"ok" if ok else b"fail")
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
