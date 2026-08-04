#!/bin/bash
# Chon he dieu hanh cho lan khoi dong sau, tu chinh pmOS dang chay.
#   ./reboot-to.sh pmos      -> ghi BCB "boot-recovery", LK nap phan vung recovery (pmOS)
#   ./reboot-to.sh lineage   -> xoa BCB, LK nap phan vung boot (LineageOS)
#   them --now de khoi dong lai ngay
#
# BCB = bootloader control block, nam o dau phan vung misc:
#   struct bootloader_message { char command[32]; char status[32]; char recovery[768]; ... }
# LK cua MediaTek doc truong command[] de quyet dinh nap boot hay recovery.
set -euo pipefail

HOST=172.16.42.1
USER_=user
PASS="${PMOS_PASS:-147147}"   # ghi de bang bien moi truong PMOS_PASS
MISC=/dev/disk/by-partlabel/misc

red(){ printf '\033[31m%s\033[0m\n' "$*"; }
grn(){ printf '\033[32m%s\033[0m\n' "$*"; }

TARGET="${1:?Dung: $0 pmos|lineage [--now]}"
case "$TARGET" in
  pmos)    CMD="boot-recovery" ;;
  lineage) CMD="" ;;
  *)       red "Chi nhan 'pmos' hoac 'lineage'"; exit 1 ;;
esac

SSH="sshpass -p $PASS ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null $USER_@$HOST"

grn ">>> BCB hien tai:"
$SSH "echo $PASS | sudo -S dd if=$MISC bs=32 count=1 2>/dev/null" | tr -d '\0' | sed 's/^/    /'

grn ">>> Dat command[] = '${CMD:-<rong>}'"
$SSH "echo $PASS | sudo -S sh -c '
    printf \"%-32s\" \"$CMD\" | tr \" \" \"\\0\" | dd of=$MISC bs=32 count=1 conv=notrunc 2>/dev/null
    sync
'"

grn ">>> BCB sau khi ghi:"
$SSH "echo $PASS | sudo -S dd if=$MISC bs=32 count=1 2>/dev/null" | tr -d '\0' | sed 's/^/    /'

if [ "${2:-}" = "--now" ]; then
  grn ">>> Khoi dong lai..."
  # busybox `reboot` o day tat han may; sysrq 'b' reset that su.
  $SSH "echo $PASS | sudo -S sh -c 'sync; echo 1 > /proc/sys/kernel/sysrq; echo b > /proc/sysrq-trigger'" || true
fi

# ---------------------------------------------------------------------------
# Neu BCB dang rong thi may boot vao LineageOS, luc do script nay khong dung
# duoc nua (no can pmOS dang chay de SSH vao). Quay lai pmOS tu LineageOS:
#
#   adb root
#   adb shell 'printf "%-32s" boot-recovery | tr " " "\0" \
#       | dd of=/dev/block/by-name/misc conv=notrunc'
#   adb reboot
#
# Hoac don gian: adb reboot recovery
# ---------------------------------------------------------------------------
