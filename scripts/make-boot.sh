#!/bin/bash
# Lay boot.img pmbootstrap vua tao tren ctdagent, va cmdline cho khop the SD hien co,
# roi gan footer AVB. Ket qua: boot-<ten>.img san sang nap.
#   ./make-boot.sh <ten>
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
NAME="${1:?Dung: $0 <ten>}"
OUT="$DIR/boot-$NAME.img"
REMOTE=ctdagent:'~/.local/var/pmbootstrap/chroot_rootfs_xiaomi-merlin/boot/boot.img'

# UUID cua the SD dang cam. `pmbootstrap install` sinh UUID moi moi lan chay, nen
# cmdline trong boot.img luon lech voi the -> phai ghi de.
BOOT_UUID=b0d4f673-c1d9-43d1-bb20-312d3b690ff6
ROOT_UUID=6f189526-2747-49e1-949a-a64a07bc7e89
CMDLINE="console=tty0 loglevel=7 log_buf_len=8M panic=20 consoleblank=0 bootopt=64S3,32N2,64N2 pmos_boot_uuid=$BOOT_UUID pmos_root_uuid=$ROOT_UUID"

grn(){ printf '\033[32m%s\033[0m\n' "$*"; }

grn ">>> Lay boot.img..."
scp -q "$REMOTE" "$OUT"
[ "$(head -c8 "$OUT")" = "ANDROID!" ] || { echo "khong phai Android boot image"; exit 1; }

grn ">>> Va cmdline (offset 64, dai 512)..."
python3 - "$OUT" "$CMDLINE" <<'EOF'
import sys
path, cmd = sys.argv[1], sys.argv[2].encode()
assert len(cmd) < 512, f'cmdline dai {len(cmd)} byte, toi da 511'
d = bytearray(open(path, 'rb').read())
print('   cu :', bytes(d[64:576]).split(b'\0')[0].decode())
d[64:576] = cmd + b'\0' * (512 - len(cmd))
open(path, 'wb').write(d)
print('   moi:', cmd.decode())
EOF

grn ">>> Gan footer AVB (LK bat buoc, thieu la lk_crash)..."
python3 "$DIR/avbtool.py" add_hash_footer --image "$OUT" \
  --partition_name recovery --partition_size 67108864 --algorithm NONE
tail -c 4096 "$OUT" | grep -qa AVBf || { echo "khong thay footer AVBf"; exit 1; }

grn ">>> Xong: $OUT"
ls -l "$OUT"
echo
echo "Nap va khoi dong lai:"
echo "  $DIR/flash-over-ssh.sh $OUT && $DIR/reboot-to.sh pmos --now"
