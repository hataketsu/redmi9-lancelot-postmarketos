#!/usr/bin/env python3
"""Dong goi u-boot.bin thanh Android boot image cho LK cua MediaTek.

Khong dung mkbootimg va cung khong tu dat cac dia chi nap: lay nguyen header cua
mot boot.img da biet chac boot duoc tren may nay, chi thay phan kernel. Nho vay
moi truong dia chi (kernel/ramdisk/tags/dtb) chac chan giong het ban goc.

Hai cho de sai, ca hai deu lam LK chet cam:
  - ramdisk_size = 0  -> lk_crash. Phai giu lai ramdisk cua anh mau.
  - thieu footer AVB  -> lk_crash. Chay avbtool sau khi dong goi.

  ./pack-uboot-boot.py <anh-mau.img> <u-boot.bin> <ket-qua.img>
"""
import struct
import sys

MAGIC = b"ANDROID!"


def roundup(n, page):
    return (n + page - 1) // page * page


def main(template, uboot, out):
    d = bytearray(open(template, "rb").read())
    if bytes(d[:8]) != MAGIC:
        sys.exit(f"{template}: khong phai Android boot image")

    (kernel_size, kernel_addr, ramdisk_size, ramdisk_addr,
     second_size, second_addr, tags_addr, page_size,
     header_version) = struct.unpack_from("<9I", d, 8)

    dtb_size, = struct.unpack_from("<I", d, 1648)

    print(f"anh mau     : {template}")
    print(f"  page_size {page_size}  header v{header_version}")
    print(f"  kernel  {kernel_size:>9} B @ {kernel_addr:#010x}")
    print(f"  ramdisk {ramdisk_size:>9} B @ {ramdisk_addr:#010x}")
    print(f"  second  {second_size:>9} B")
    print(f"  dtb     {dtb_size:>9} B")

    if ramdisk_size == 0:
        sys.exit("anh mau khong co ramdisk: LK se bao lk_crash")

    hdr_pages = roundup(1648 + 12, page_size)
    off = hdr_pages
    kernel_off = off
    off += roundup(kernel_size, page_size)
    ramdisk_off = off
    off += roundup(ramdisk_size, page_size)
    second_off = off
    off += roundup(second_size, page_size)
    dtb_off = off

    ramdisk = bytes(d[ramdisk_off:ramdisk_off + ramdisk_size])
    second = bytes(d[second_off:second_off + second_size])
    dtb = bytes(d[dtb_off:dtb_off + dtb_size])

    new_kernel = open(uboot, "rb").read()
    if new_kernel[56:60] != b"ARM\x64":
        print("  canh bao: khong thay magic ARM64 o offset 56 cua u-boot.bin;"
              " can CONFIG_LINUX_KERNEL_IMAGE_HEADER=y")
    print(f"u-boot      : {uboot}  {len(new_kernel)} B")

    head = bytearray(d[:hdr_pages])
    struct.pack_into("<I", head, 8, len(new_kernel))

    img = bytearray()
    img += head
    img += new_kernel + b"\0" * (roundup(len(new_kernel), page_size) - len(new_kernel))
    img += ramdisk + b"\0" * (roundup(len(ramdisk), page_size) - len(ramdisk))
    if second:
        img += second + b"\0" * (roundup(len(second), page_size) - len(second))
    if dtb:
        img += dtb + b"\0" * (roundup(len(dtb), page_size) - len(dtb))

    open(out, "wb").write(bytes(img))
    print(f"ket qua     : {out}  {len(img)} B")
    print()
    print("Buoc tiep (bat buoc, thieu la lk_crash):")
    print(f"  python3 avbtool.py add_hash_footer --image {out} \\")
    print("      --partition_name recovery --partition_size 67108864 --algorithm NONE")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:4])
