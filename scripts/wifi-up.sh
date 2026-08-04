#!/bin/sh
# Bat WiFi tren Redmi 9 (lancelot) chay postmarketOS. Chay bang root.
#   wifi-up.sh <ssid> <mat khau>
#
# Ngan xep connectivity cua MediaTek can hai manh userspace ma pmOS khong co
# (binary vendor la bionic, khong chay tren musl). Ca hai da duoc viet lai:
#
#   wmt_loader.py    ioctl len /dev/wmtdetect de nap driver chip
#                    -> tao /dev/stpwmt, /dev/wmtWifi
#   wmt_launcher.py  ioctl SET_STP_MODE (bao STP chay tren BTIF), roi tra loi
#                    lenh "srh_rom_patch" kernel gui len khi bat nguon chip
#
# Thu tu bat buoc: detect -> launcher chay nen -> echo 1 > /dev/wmtWifi.
# Bang ROM patch trong kernel chi nap mot lan; nap sai file thi phai reboot.
set -e

SSID="${1:?Dung: $0 <ssid> <mat khau>}"
PSK="${2:?Dung: $0 <ssid> <mat khau>}"
LAUNCHER=/usr/local/bin/wmt_launcher.py

running() {
    for p in /proc/[0-9]*; do
        tr '\0' '\n' < "$p/cmdline" 2>/dev/null | grep -qx "$LAUNCHER" && return 0
    done
    return 1
}

echo ">>> 1. Nap driver chip connectivity"
if [ ! -e /dev/wmtWifi ]; then
    python3 /usr/local/bin/wmt_loader.py || true
fi
[ -e /dev/wmtWifi ] || { echo "!! /dev/wmtWifi chua co, driver wlan chua dang ky" >&2; exit 1; }

echo ">>> 2. Khoi dong launcher"
if ! running; then
    setsid python3 "$LAUNCHER" > /tmp/launcher.log 2>&1 < /dev/null &
    sleep 3
fi
sed 's/^/    /' /tmp/launcher.log

echo ">>> 3. Bat nguon WiFi"
if ! echo 1 > /dev/wmtWifi 2>/dev/null; then
    echo "!! bat nguon that bai. Log launcher va kernel:" >&2
    sed 's/^/    /' /tmp/launcher.log >&2
    dmesg | grep -iE "WMT-CORE|WMT-IC|MTK-WIFI" | tail -15 >&2
    exit 1
fi
sleep 3

IF=$(ls /sys/class/net | grep -E '^wlan' | head -1)
[ -n "$IF" ] || { echo "!! khong thay giao dien wlan" >&2; exit 1; }
echo ">>> 4. Giao dien: $IF"
ip link set "$IF" up

mkdir -p /etc/wpa_supplicant
CONF=/etc/wpa_supplicant/wpa_supplicant-$IF.conf
{
    echo "ctrl_interface=/var/run/wpa_supplicant"
    echo "update_config=1"
    echo
    wpa_passphrase "$SSID" "$PSK"
} > "$CONF"
chmod 600 "$CONF"

pkill -x wpa_supplicant 2>/dev/null || true
sleep 1
wpa_supplicant -B -i "$IF" -c "$CONF" -D nl80211,wext

echo ">>> 5. Cho ket noi"
i=0
while [ $i -lt 25 ]; do
    wpa_cli -i "$IF" status 2>/dev/null | grep -q "wpa_state=COMPLETED" && break
    i=$((i + 1)); sleep 1
done

udhcpc -i "$IF" -n -q 2>/dev/null || dhcpcd "$IF" 2>/dev/null || \
    echo "!! khong lay duoc IP tu DHCP"

echo ">>> Trang thai:"
wpa_cli -i "$IF" status 2>/dev/null | grep -E "wpa_state|^ssid|ip_address" || true
ip addr show "$IF" | grep -E "inet |state" || true
