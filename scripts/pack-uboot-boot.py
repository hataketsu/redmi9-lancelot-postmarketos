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
import gzip
import hashlib
import io
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

    payload = open(uboot, "rb").read()
    if payload[56:60] != b"ARM\x64":
        print("  canh bao: khong thay magic ARM64 o offset 56 cua u-boot.bin;"
              " can CONFIG_LINUX_KERNEL_IMAGE_HEADER=y")
    print(f"u-boot      : {uboot}  {len(payload)} B")

    # LK cua may nay GIAI NEN kernel truoc khi nhay vao. Anh mau bat dau bang
    # 1f 8b 08 -> gzip. Nhet mot ARM64 Image tho vao thi bo giai nen cua LK sap
    # va may bao androidboot.bootreason=lk_crash, chua kip chay dong lenh nao.
    kernel_orig = bytes(d[kernel_off:kernel_off + kernel_size])
    if kernel_orig[:3] == b"\x1f\x8b\x08":
        buf = io.BytesIO()
        # mtime=0 cho ket qua lap lai duoc
        with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as g:
            g.write(payload)
        new_kernel = buf.getvalue()
        print(f"  anh mau la kernel gzip -> nen u-boot lai: {len(new_kernel)} B")
    else:
        new_kernel = payload
        print("  anh mau la kernel tho -> giu nguyen")

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

    # Truong id la SHA1 chay qua tung phan kem do dai. Giu nguyen id cua anh mau
    # thi no khong con khop noi dung moi.
    sha = hashlib.sha1()
    for part in (new_kernel, ramdisk, second):
        sha.update(part)
        sha.update(struct.pack("<I", len(part)))
    if dtb:
        sha.update(dtb)
        sha.update(struct.pack("<I", len(dtb)))
    digest = sha.digest()
    img[576:576 + 32] = digest + b"\0" * (32 - len(digest))
    print(f"  id (SHA1) tinh lai: {digest.hex()}")

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
