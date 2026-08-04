#!/usr/bin/env python3
"""Doc lai log cua U-Boot sau khi may khoi dong lai.

Redmi 9 khong co UART nao voi toi duoc ma khong thao may, nen U-Boot ghi console
vao RAM roi doi Linux doc ho. Co hai duong, doc ca hai:

  1. /sys/fs/pstore/console-ramoops - duong chinh, khong can cong cu gi
  2. doc thang 0x4d05f000 qua /dev/mem - dung khi pstore chua kip phoi ra,
     hoac khi muon xem noi dung ngay trong lan boot hien tai

Ca hai deu tro toi mot cho: vung console cua ramoops, dinh dang
persistent_ram_buffer. Duoi vung framebuffer thi KHONG dung duoc - lk ve logo
len do va se xoa mat log ngay o lan reset sau khi treo.

Chay tren may bang root:  read-uboot-log.py
"""
import os
import struct
import sys

MEMLOG_BASE = 0x4D05F000        # vung console cua ramoops
MEMLOG_SIZE = 0x00040000
MEMLOG_MAGIC = 0x43474244          # "DBGC", PERSISTENT_RAM_SIG cua Linux
HDR = struct.Struct("<III")        # sig, start, size (persistent_ram_buffer)


def read_memlog():
    """Doc thang vung ramoops qua /dev/mem.

    Dung pread chu khong mmap: vung nay la reserved memory, mmap no roi cham vao
    la an SIGBUS (khong bat duoc trong Python), con pread thi chi tra ve loi.
    """
    if not os.path.exists("/dev/mem"):
        return "khong co /dev/mem (can CONFIG_DEVMEM=y)"
    try:
        fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    except PermissionError:
        return "khong doc duoc /dev/mem (can root)"
    try:
        try:
            head = os.pread(fd, HDR.size, MEMLOG_BASE)
        except OSError as exc:
            return f"khong doc duoc {MEMLOG_BASE:#x}: {exc}"
        if len(head) < HDR.size:
            return f"doc thieu tai {MEMLOG_BASE:#x}"
        magic, length, _mirror = HDR.unpack(head)
        if magic != MEMLOG_MAGIC:
            return (f"khong thay chu ky DBGC tai {MEMLOG_BASE:#x} "
                    f"(doc duoc {magic:#010x})")
        length = min(length, MEMLOG_SIZE - HDR.size)
        out = []
        pos = 0
        while pos < length:
            chunk = os.pread(fd, min(0x1000, length - pos),
                             MEMLOG_BASE + HDR.size + pos)
            if not chunk:
                break
            out.append(chunk)
            pos += len(chunk)
        return f"[{length} byte]\n" + b"".join(out).decode(errors="replace")
    finally:
        os.close(fd)


def read_ramoops():
    path = "/sys/fs/pstore"
    if not os.path.isdir(path):
        return "khong co /sys/fs/pstore"
    out = []
    try:
        names = sorted(os.listdir(path))
    except PermissionError:
        return "khong doc duoc /sys/fs/pstore (can root)"
    for name in names:
        if "console" not in name and "dmesg" not in name:
            continue
        try:
            with open(os.path.join(path, name), errors="replace") as f:
                body = f.read()
        except OSError as exc:
            body = f"(khong doc duoc: {exc})"
        out.append(f"--- {name} ---\n{body}")
    return "\n".join(out) if out else "(khong co ban ghi console nao)"


def main():
    print("=" * 60)
    print("memlog (0x%08x)" % MEMLOG_BASE)
    print("=" * 60)
    print(read_memlog())
    print()
    print("=" * 60)
    print("ramoops / pstore")
    print("=" * 60)
    print(read_ramoops())


if __name__ == "__main__":
    sys.exit(main())
