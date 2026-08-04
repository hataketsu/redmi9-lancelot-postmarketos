#!/bin/bash
# Nap boot.img vao partition recovery tu chinh pmOS dang chay, khong can fastboot.
#   ./flash-over-ssh.sh boot-xxx-avb.img [--reboot]
#
# Yeu cau: may dang chay pmOS va SSH duoc tai 172.16.42.1.
# Neu anh nay lam may khong boot duoc nua, van con duong fastboot cu de cuu.
set -euo pipefail

HOST=172.16.42.1
USER_=user
PASS="${PMOS_PASS:-147147}"   # ghi de bang bien moi truong PMOS_PASS
PART=/dev/mmcblk0p1          # by-partlabel/recovery
PART_SIZE=67108864

red(){ printf '\033[31m%s\033[0m\n' "$*"; }
grn(){ printf '\033[32m%s\033[0m\n' "$*"; }

IMG="${1:?Dung: $0 <boot.img> [--reboot]}"
[ -f "$IMG" ] || { red "Khong thay $IMG"; exit 1; }

SZ=$(stat -c %s "$IMG")
[ "$SZ" -le "$PART_SIZE" ] || { red "Anh $SZ B > partition $PART_SIZE B"; exit 1; }
[ "$(head -c8 "$IMG")" = "ANDROID!" ] || { red "$IMG khong phai Android boot image"; exit 1; }

# AVB footer bat buoc, khong co thi LK crash (xem README muc 1).
tail -c 67108864 "$IMG" 2>/dev/null | grep -qa AVBf \
  || tail -c 4096 "$IMG" | grep -qa AVBf \
  || red "CANH BAO: khong thay footer AVBf — LK co the crash. Chay avbtool add_hash_footer truoc."

SSH="sshpass -p $PASS ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null $USER_@$HOST"

grn ">>> Kiem tra may song..."
$SSH true

grn ">>> Chep $IMG ($SZ B) sang /tmp tren may..."
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    "$IMG" "$USER_@$HOST:/tmp/new-boot.img"

LOCAL_MD5=$(md5sum "$IMG" | cut -d' ' -f1)
REMOTE_MD5=$($SSH 'md5sum /tmp/new-boot.img' | cut -d' ' -f1)
[ "$LOCAL_MD5" = "$REMOTE_MD5" ] || { red "MD5 lech sau khi chep: $LOCAL_MD5 != $REMOTE_MD5"; exit 1; }
grn "    md5 khop: $LOCAL_MD5"

grn ">>> Ghi vao $PART (recovery)..."
$SSH "echo $PASS | sudo -S sh -c '
    dd if=/tmp/new-boot.img of=$PART bs=1M conv=fsync 2>&1 | tail -1
    sync
'"

grn ">>> Doc lai de kiem chung..."
MB=$(( (SZ + 1048575) / 1048576 ))
BACK_MD5=$($SSH "echo $PASS | sudo -S dd if=$PART bs=1M count=$MB 2>/dev/null | head -c $SZ | md5sum" | cut -d' ' -f1)
if [ "$BACK_MD5" = "$LOCAL_MD5" ]; then
  grn "    OK — noi dung tren eMMC khop anh goc."
else
  red "    LECH: doc lai duoc $BACK_MD5, mong doi $LOCAL_MD5"
  red "    eMMC nay da mon (life_time 0x0b). Ghi lai hoac quay ve fastboot."
  exit 1
fi

$SSH 'rm -f /tmp/new-boot.img'

if [ "${2:-}" = "--reboot" ]; then
  grn ">>> Khoi dong lai vao recovery..."
  # busybox `reboot` tren OpenRC o day tat may han, khong khoi dong lai.
  # sysrq 'b' reset thang sau khi sync.
  $SSH "echo $PASS | sudo -S sh -c 'sync; echo 1 > /proc/sys/kernel/sysrq; echo b > /proc/sysrq-trigger'" || true
  echo "Doi may len lai roi: sshpass -p $PASS ssh $USER_@$HOST"
else
  echo
  echo "Xong. Khoi dong lai bang:"
  echo "  $SSH \"echo $PASS | sudo -S reboot\""
fi
