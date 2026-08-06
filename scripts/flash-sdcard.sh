#!/bin/bash
# Ghi postmarketOS vao the microSD, roi boot bang fastboot.
# eMMC KHONG bi ghi mot byte nao.
#
#   sudo ./flash-sdcard.sh
#
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
BOOT_GZ="$DIR/xiaomi-merlin-boot.img.gz"    # ext2, label pmOS_boot,  512 MiB
ROOT_GZ="$DIR/xiaomi-merlin-root.img.gz"    # ext4, label pmOS_root,  754 MiB

red(){ printf '\033[31m%s\033[0m\n' "$*"; }
grn(){ printf '\033[32m%s\033[0m\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { red "Phai chay bang sudo."; exit 1; }
for f in "$BOOT_GZ" "$ROOT_GZ"; do
  [ -f "$f" ] || { red "Thieu file: $f"; exit 1; }
  gzip -t "$f" || { red "File hong: $f"; exit 1; }
done

# ---- chon the, KHONG hardcode disk6 vi so hieu doi moi lan cam ----
echo "Cac o ngoai dang cam:"
diskutil list external physical
echo
read -r -p "Nhap dinh danh the (vd: disk6), KHONG co /dev/: " DISK
DEV="/dev/$DISK"
RDEV="/dev/r$DISK"

# ---- kiem tra an toan ----
[ -b "$DEV" ] || { red "$DEV khong ton tai."; exit 1; }
INFO=$(diskutil info "$DEV")
grep -q "Whole:  *Yes"        <<<"$INFO" || { red "$DEV khong phai o hoan chinh."; exit 1; }
grep -qE "Removable Media: *(Removable|Yes)|Ejectable: *Yes" <<<"$INFO" \
  || { red "$DEV khong phai o thao roi duoc. DUNG LAI."; exit 1; }
SIZE=$(diskutil info -plist "$DEV" | plutil -extract TotalSize raw -)
[ "$SIZE" -lt 128000000000 ] || { red "$DEV lon hon 128GB — nghi la o cung. DUNG LAI."; exit 1; }
[ "$SIZE" -gt 4000000000 ]   || { red "$DEV nho hon 4GB — khong du cho."; exit 1; }

echo
red "=== SE XOA TOAN BO $DEV ($((SIZE/1000000000)) GB) ==="
diskutil list "$DEV"
read -r -p 'Go dung chu XOA de tiep tuc: ' OK
[ "$OK" = "XOA" ] || { echo "Huy."; exit 1; }

# ---- tao bang phan vung: p1 600M cho pmOS_boot, p2 phan con lai cho pmOS_root ----
# Tao bang FAT32 chi de lay ban ghi MBR dung chuan; ext2/ext4 se ghi de len sau.
grn ">>> Tao phan vung..."
diskutil unmountDisk force "$DEV"
diskutil partitionDisk "$DEV" MBRFormat \
  "MS-DOS FAT32" PMBOOT 600M \
  "MS-DOS FAT32" PMROOT R
diskutil unmountDisk force "$DEV"

# ---- ghi anh ----
# macOS tu mount lai phan vung FAT ngay sau khi bang phan vung thay doi, va dd vao
# phan vung dang mount se bi tu choi "Resource busy". Nen unmount ngay truoc moi lan ghi.
write_img() {  # $1=file.gz  $2=hau to phan vung  $3=ten
  grn ">>> Ghi $3 vao ${DEV}$2 ..."
  diskutil unmount force "${DEV}$2" 2>/dev/null || true
  diskutil unmountDisk force "$DEV" 2>/dev/null || true
  if ! gunzip -c "$1" | dd of="${RDEV}$2" bs=4m; then
    red "GHI THAT BAI vao ${DEV}$2"
    red "Neu bao 'Resource busy': chay lai script, hoac unmount tay roi thu lai."
    exit 1
  fi
  sync
  # Kiem chung: doc nhan tu superblock ext (offset 1024+120).
  # PHAI dung /dev/diskN (co dem) chu KHONG phai /dev/rdiskN — thiet bi tho tren macOS
  # chi cho doc theo boi so block, `bs=1 skip=...` se that bai.
  local L
  L=$(dd if="${DEV}$2" bs=512 skip=2 count=1 2>/dev/null | dd bs=1 skip=120 count=16 2>/dev/null | tr -d '\0')
  if [ "$L" = "$3" ]; then
    grn "    OK — nhan doc lai duoc: '$L'"
  else
    red "    SAI — doc lai nhan duoc '$L', mong doi '$3'. Dung lai."
    exit 1
  fi
}

write_img "$BOOT_GZ" s1 pmOS_boot
write_img "$ROOT_GZ" s2 pmOS_root

diskutil unmountDisk force "$DEV" 2>/dev/null || true
grn ">>> XONG. Rut the, cam vao dien thoai."
cat <<'NEXT'

Buoc tiep theo tren dien thoai:

  1. Cam the vao dien thoai.
  2. Vao fastboot:  tat may han, giu Vol Down + Nguon.
  3. Tren Mac:

       cd ~/Projects/redmi9/pmos
       fastboot devices                        # phai thay may
       fastboot boot pmos-boot-android.img     # nap vao RAM, KHONG ghi eMMC

Khong len duoc thi rut pin, bat lai -> LineageOS nguyen ven.

Len duoc thi vao bang USB:

       ssh user@172.16.42.1        # mat khau: xem $PMOS_PASS

NEXT
