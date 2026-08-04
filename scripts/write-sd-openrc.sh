#!/bin/bash
# Ghi rootfs postmarketOS (OpenRC) vao the microSD.
#   sudo ./write-sd-openrc.sh /dev/sdX
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
BOOT_GZ="$DIR/openrc-boot.img.gz"   # ext2, nhan pmOS_boot
ROOT_GZ="$DIR/openrc-root.img.gz"   # ext4, nhan pmOS_root

red(){ printf '\033[31m%s\033[0m\n' "$*"; }
grn(){ printf '\033[32m%s\033[0m\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { red "Phai chay bang sudo."; exit 1; }
[ $# -eq 1 ] || { red "Dung: sudo $0 /dev/sdX"; exit 1; }
DEV="$1"

for f in "$BOOT_GZ" "$ROOT_GZ"; do
  [ -f "$f" ] || { red "Thieu $f"; exit 1; }
  gzip -t "$f" || { red "Hong: $f"; exit 1; }
done

# --- chan an toan ---
[ -b "$DEV" ] || { red "$DEV khong phai block device"; exit 1; }
BASE="$(basename "$DEV")"
[ "$(cat /sys/block/$BASE/removable 2>/dev/null || echo 0)" = "1" ] \
  || { red "$DEV khong phai o thao roi duoc. DUNG LAI."; exit 1; }
SIZE=$(blockdev --getsize64 "$DEV")
[ "$SIZE" -lt 128000000000 ] || { red "$DEV > 128GB, nghi la o cung. DUNG LAI."; exit 1; }
[ "$SIZE" -gt 4000000000 ]   || { red "$DEV < 4GB, khong du cho."; exit 1; }

echo
red "=== SE XOA TOAN BO $DEV ($((SIZE/1000000000)) GB) ==="
lsblk -o NAME,SIZE,FSTYPE,LABEL "$DEV"
read -r -p 'Go dung chu XOA de tiep tuc: ' OK
[ "$OK" = "XOA" ] || { echo "Huy."; exit 1; }

umount "${DEV}"* 2>/dev/null || true

grn ">>> Tao bang phan vung (600M boot + phan con lai cho root)..."
sfdisk "$DEV" <<'EOF'
label: dos
,600M,83
,,83
EOF
partprobe "$DEV"; sleep 2

grn ">>> Ghi pmOS_boot -> ${DEV}1"
gunzip -c "$BOOT_GZ" | dd of="${DEV}1" bs=4M conv=fsync status=progress
grn ">>> Ghi pmOS_root -> ${DEV}2"
gunzip -c "$ROOT_GZ" | dd of="${DEV}2" bs=4M conv=fsync status=progress
sync; partprobe "$DEV"; sleep 2

grn ">>> Kiem chung nhan va UUID:"
blkid "${DEV}1" "${DEV}2"

cat <<'NEXT'

Mong doi:
  ${DEV}1  LABEL="pmOS_boot"  UUID=b0d4f673-c1d9-43d1-bb20-312d3b690ff6
  ${DEV}2  LABEL="pmOS_root"  UUID=6f189526-2747-49e1-949a-a64a07bc7e89

Buoc tiep: rut the, cam vao dien thoai, vao fastboot,
roi flash boot-openrc-avb.img vao partition recovery.
NEXT
