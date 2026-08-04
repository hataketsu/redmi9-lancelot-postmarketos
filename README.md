# postmarketOS on Xiaomi Redmi 9 (lancelot, MT6769T)

Notes, patches and evidence from bringing postmarketOS up on a Xiaomi Redmi 9
(`lancelot`, MediaTek Helio G80 — the kernel reports `Machine model: MT6769T`).

There is no upstream postmarketOS port for `lancelot`. This work reuses the
**archived** `xiaomi-merlin` port (Redmi Note 9), which builds from the same
`LineageOS/android_kernel_xiaomi_mt6768` tree and — verified with
`pmbootstrap bootimg_analyze` against LineageOS's own `boot.img` — uses
identical boot image offsets:

```
flash_offset_base 0x40078000   kernel 0x00008000   ramdisk 0x07c08000
flash_offset_dtb  0x0bc08000   tags   0x0bc08000   second  0xbff88000
pagesize 2048   header_version 2
```

Status: **working.** postmarketOS boots from a microSD card with OpenRC, the panel and
framebuffer console come up, and SSH over USB works. The worn-out eMMC holds only the
small read-only `boot` partition.

```
PRETTY_NAME  postmarketOS edge
kernel       4.14.320 #1-postmarketOS aarch64
init         OpenRC
rootfs       /dev/mmcblk1p2   28.3G on /
network      SSH at 172.16.42.1 over USB RNDIS
display      fb0 1088x7104, fbcon bound, KTD3137 backlight
```

---

## Blockers found, and how each was proven

Every claim here is backed by a log in [`logs/`](logs/).

### 1. `lk_crash` with every image — missing AVB footer

MediaTek's LK bootloader parses the Android Verified Boot structure **even with an
unlocked bootloader**. pmbootstrap does not emit one, so LK crashes before the
kernel runs (`ro.boot.bootreason=lk_crash`).

```sh
python3 avbtool.py add_hash_footer --image boot.img \
  --partition_name recovery --partition_size 67108864 --algorithm NONE
```

LineageOS's own `boot.img` uses `Algorithm: NONE`, so no signing key is needed.
`avbtool.py` comes from AOSP `external/avb`.

### 2. Kernel oops when a USB cable is plugged in — smb1351 charger

```
[27.715171] Unable to handle kernel NULL pointer dereference at virtual address 00000020
Call trace:
  smb1351_float_chg_det_work+0x3c/0x138
```

`charger_manager_get_by_name("charger_port1")` returns NULL, the probe only warns
and continues, and two later sites dereference `chip->chg_consumer->cm`.
Fix: [`patches/smb1351-null-guard.patch`](patches/smb1351-null-guard.patch).

### 3. Never reaches `/init` — `drcc_init` hangs

Found by adding `initcall_debug` to the kernel cmdline. The last `calling` line has
no matching `returned`:

```
[0.943525] calling  deferred_probe_initcall+0x0/0x44 @ 1
[0.949224] initcall deferred_probe_initcall+0x0/0x44 returned 0 after 5550 usecs
[0.949239] calling  drcc_init+0x0/0xdc @ 1
                                            <- no "returned" line, ever
```

`drcc_init` is a `late_initcall` in
`drivers/misc/mediatek/base/power/drcc_v1/mt6768/mtk_drcc.c`. DRCC is a CPU voltage
optimisation and is not needed to boot.
Fix: [`patches/drcc-skip-init.patch`](patches/drcc-skip-init.patch).

### 4. systemd freezes at 7 s — the current blocker

```
[1.357419] Freeing unused kernel memory: 4544K
[7.039585] [pmOS-rd]: Mount root partition (/dev/mmcblk1p2) to /sysroot (read-write)
[7.228224] systemd[1]: Failed to determine whether /proc is a mount point: No error information
[7.228276] systemd[1]: Failed to determine whether /sys is a mount point: No error information
[7.228298] systemd[1]: Failed to determine whether /dev is a mount point: No error information
[7.236607] systemd[1]: Freezing execution.
```

Mount and `switch_root` both succeed; systemd starts as PID 1 and freezes.

`CONFIG_FHANDLE` was missing (every other systemd requirement — `CGROUPS`,
`INOTIFY_USER`, `SIGNALFD`, `TIMERFD`, `EPOLL`, `DEVTMPFS`, `SECCOMP_FILTER` — was
already `=y`). **Enabling it did not help**: the same freeze reappears, and the
initramfs log shows the deeper problem:

```
[pmOS-rd]: Failed to chase and open directory '/etc//udev/udev.conf.d': No error information
[pmOS-rd]: Failed to scan devices: No error information
```

systemd's `chase()` uses **`openat2()`, which only exists from kernel 5.6**. This is
a 4.14 downstream kernel, so there is nothing to enable. The `No error information`
string is musl's `strerror` for the resulting errno.

**Conclusion: modern systemd cannot run on this kernel. Use OpenRC**
(`pmbootstrap config service_manager openrc`).

### 5. Black screen — three separate causes stacked

Once the system booted, the panel stayed dark. Three independent problems, each hiding
the next:

**a. `/dev/fb0` reported size `0,0`.** The kernel was built with merlin's config, whose
`CONFIG_CUSTOM_KERNEL_LCM` lists Redmi Note 9 panels. lancelot's panels carry a `_j19`
suffix, so no driver matched the `LCM_name=` that LK passes on the cmdline:

```
kernel had (merlin):  nt36672A_fhdp_dsi_vdo_tianma
device reports:       nt36672A_fhdp_dsi_vdo_tianma_j19_lcm_drv
```

Fix — use lancelot's list:

```
CONFIG_CUSTOM_KERNEL_LCM="nt36672A_fhdp_dsi_vdo_tianma_j19 ft8719_fhdp_dsi_vdo_huaxing_j19 nt36672A_fhdp_dsi_vdo_dijing_j19 nt36672D_fhdp_dsi_vdo_dijing_j19"
```

After this `fb0` came up as `1088,7104` — matching LineageOS — and the KTD3137 backlight
driver appeared.

**b. Backlight defaults to 0, and is not where you expect it.** It lives under
`/sys/class/leds/lcd-backlight`, **not** `/sys/class/backlight/`, so ordinary brightness
tools never see it. Range is 0–2047 and it boots at 0, so the panel is alive but black.
Persist it with `/etc/local.d/backlight.start` (the `local` service is already in the
`default` runlevel).

**c. `CONFIG_FRAMEBUFFER_CONSOLE` was not set.** Everything *looked* right — `/dev/fb0`
writable at 74 MB/s, backlight on, `getty` running on tty1 — yet text written to
`/dev/tty1` never appeared. The giveaway is the vtconsole binding:

```
before:  vtcon0 -> (S) dummy device        bind=1     # only the dummy
after:   vtcon0 -> (S) dummy device        bind=0
         vtcon1 -> (M) frame buffer device bind=1     # fbcon attached
```

Enable `CONFIG_FRAMEBUFFER_CONSOLE=y` and `CONFIG_FRAMEBUFFER_CONSOLE_DETECT_PRIMARY=y`.
`CONFIG_FONT_TER16x32=y` plus `fbcon=font:TER16x32` on the cmdline makes the console
legible on a 1080x2340 panel — the default 8x16 font is pinhead-sized.

Result: the Tux boot logos render (one per CPU core) and the login prompt is usable.

### 6. No touchscreen — wrong driver variant, then missing firmware

`/proc/bus/input/devices` listed no touch device at all. Two separate causes.

**a. merlin's config selects a different driver for the same chip.** Both devices use
a Novatek NT36672, but the kernel tree carries two independent forks of that driver:

```
merlin  : CONFIG_TOUCHSCREEN_NT36xxx_HOSTDL_SPI=y   CONFIG_TOUCHSCREEN_FTS=y
lancelot: CONFIG_TOUCHSCREEN_MTK_NT36672=y          CONFIG_TOUCHSCREEN_MTK_FT8719P=y
```

They cannot coexist — the forks share global symbol names (`ts`, `nvt_gesture_flag`,
`ENG_RST_ADDR`, `fts_gesture_flag`), so enabling both fails at link with
`multiple definition`. Enable lancelot's pair and disable merlin's.

Related trap: the *display* driver depends on the *touch* driver.
`drivers/misc/mediatek/video/mt6768/videox/disp_recovery.c:708` declares
`extern int32_t nvt_update_firmware(...)` with **no `#ifdef`** and calls it
unconditionally, so disabling every touch driver breaks the vmlinux link.

**b. The NT36672 is a "no flash" part** — firmware is downloaded to it on every boot,
and postmarketOS has none:

```
[NVT-ts] update_firmware_request 314: filename is nvt_tm_fw.bin
NVT-ts spi0.0: Direct firmware load for nvt_tm_fw.bin failed with error -2
```

Extract it from the LineageOS vendor image. The OTA zip ships `vendor.new.dat.br`,
not a mountable image:

```sh
brotli -d vendor.new.dat.br -o vendor.new.dat
python3 sdat2img.py vendor.transfer.list vendor.new.dat vendor.img
debugfs -R "dump /firmware/nvt_tm_fw.bin nvt_tm_fw.bin" vendor.img
```

Pick the file matching the panel LK selected — `LCM_name=...tianma...` means
`nvt_tm_fw.bin`. Drop it in `/lib/firmware/`. Result:

```
[NVT-ts] nvt_update_firmware 1124: Update firmware success! <111378 us>
/proc/nvt_tp_info -> [Vendor]Tianma,[TP-IC]:NT36672,[FW]0x14
```

Ten-finger multitouch, protocol B, works.

### 7. No `wlan0` — MediaTek's connectivity stack is driven from userspace

The kernel config was already right (`CONFIG_MTK_COMBO_WIFI=y`,
`CONFIG_WLAN_DRV_BUILD_IN=y`, `CONFIG_MTK_COMBO_CHIP_CONSYS_6768`) and the `gen4m`
driver was built in, but nothing appeared — not even a log line. MediaTek's stack
needs two vendor daemons that postmarketOS does not have, and cannot run: they are
bionic binaries and this is a musl system. Both were reimplemented against the kernel
source. Three separate blockers, in the order they appear:

**a. The driver init aborts on an unrelated failure, once per boot.**
`do_common_drv_init()` returns the **sum** of four sub-inits, and `HIF-SDIO` always
returns `-16` here — this chip talks over AXI, not SDIO. `do_connectivity_driver_init()`
sees non-zero and returns immediately, so `do_wlan_drv_init()` never runs. Worse, it
guards itself with `static int init_before`, so it runs **exactly once per boot** — once
it has failed, further ioctls return 0 and do nothing.

[`patches/wmt-continue-init.patch`](patches/wmt-continue-init.patch) drops the early
return and promotes four `PR_DBG` lines to `PR_INFO` so the failing sub-init is visible.
After it:

```
pmOS: HIF-SDIO init ret:-16
pmOS: COMBO COMMON init ret:0 / STP-UART ret:0 / STP-SDIO ret:0
do_wlan_drv_init: WLAN-GEN4 driver init, ret:0
```

and `/dev/wmtWifi` appears.

**b. `WMT_IOCTL_SET_STP_MODE` is mandatory and fails silently if skipped.**

```
[WMT-CORE][E]wmt_core_stp_init(796): no hif info!
```

`wmt_lib_set_hif()` decodes the argument as bits `[3:0]` = STP interface, `[7:4]` = FM
mode. MT6768 runs STP over BTIF: `STP_BTIF_FULL(0x03) | (WMT_FM_COMM(2) << 4)` = `0x23`.

**c. The kernel asks *userspace* to locate the firmware.** On power-on it writes a
command string to `/dev/stpwmt` and blocks for six seconds:

```
read("/dev/stpwmt")  -> "srh_rom_patch" | "srh_patch"
                        ioctl SET_ROM_PATCH_INFO / SET_PATCH_NUM + SET_PATCH_INFO
write("ok")
```

With nobody listening: `wmt_ctrl_ul_cmd(468): wait signal timeout`.

Two traps in picking the firmware, both of which fail *after* a successful-looking
copy into EMI:

- **Wrong chip family.** `/vendor/firmware` ships both `soc1_0_*` and `soc3_0_*`. This
  chip is `soc1_0` (matching `WIFI_RAM_CODE_soc1_0_1a_1.bin`); `soc3_0_ram_mcu_*` carries
  `HwVer=0x8a10` while the chip reports `0x8a00`.
- **The low address byte.** The header is `struct wmt_rom_patch` — `u4PatchAddr` at
  offset 24, `u4PatchType` at 28 (stored big-endian; read the last byte). Every patch
  file has `0x11` as the low byte of the address and it must be cleared:

  ```
  patch_mcu 0x0001c011 -> 0x0001c000     ram_mcu  0xf0000011 -> 0xf0000000
  ram_bt    0xf0080011 -> 0xf0080000     ram_wifi 0xf0140011 -> 0xf0140000
  ```

  Leave it in and the chip loads the patch, then stops answering:

  ```
  wmt_core_init_script_retry(713): read (wmt reset) iRet(-1) evt len err(rx:0, exp:5)
  mtk_wcn_soc_sw_init(1300): init_table_3 fail(-1)
  ```

  The kernel takes the low 24 bits as an EMI offset
  (`patchEmiOffset = a[2] << 16 | a[1] << 8 | a[0]`), which yields MediaTek's standard
  layout: mcu `0x000000`, bt `0x080000`, wifi `0x140000`.

Order matters, and the kernel caches the patch table for the whole boot
(`if (!pDev->pWmtRomPatchInfo[WMTDRV_TYPE_WMT])`) — **registering the wrong file means
rebooting**, fixing userspace and retrying will not help.

```sh
wmt_loader.py             # ioctls on /dev/wmtdetect -> /dev/wmtWifi
wmt_launcher.py &         # SET_STP_MODE, then serve srh_rom_patch / srh_patch
echo 1 > /dev/wmtWifi     # -> wlan0
wpa_supplicant ...
```

All of it is wrapped in [`scripts/wifi-up.sh`](scripts/wifi-up.sh).

The MAC address is random (`5a:ca:…`, locally administered) because the NVRAM partition
is not read. It does not stop anything from working.

---

## Flashing without fastboot

Once postmarketOS boots, `fastboot` is no longer needed to iterate on the kernel.
`recovery` is `/dev/mmcblk0p1` and the default user is in `wheel`, so a new boot
image can be written from the running system:

```sh
scp boot.img phone:/tmp/ && ssh phone "sudo dd if=/tmp/boot.img of=/dev/mmcblk0p1"
```

[`scripts/flash-over-ssh.sh`](scripts/flash-over-ssh.sh) does this with the checks
that matter: the `ANDROID!` magic, the `AVBf` footer (missing it means `lk_crash`),
an md5 after the copy, and **an md5 of the data read back off the eMMC** — this eMMC
has `life_time 0x0b` (past its rated life), so silent write corruption is a real risk.
fastboot remains the recovery path if a flash goes bad.

**Choosing what to boot.** A plain `reboot` makes LK load `boot`, which is LineageOS;
postmarketOS lives in `recovery`. Write the bootloader control block to `misc`
(`/dev/mmcblk0p2`) and LK loads recovery instead:

```sh
printf '%-32s' boot-recovery | tr ' ' '\0' | dd of=/dev/mmcblk0p2 conv=notrunc
```

See [`scripts/reboot-to.sh`](scripts/reboot-to.sh).

Note that busybox `reboot` on this OpenRC image **powers the phone off** rather than
restarting it. Use `sync; echo b > /proc/sysrq-trigger`.

---

## Traps worth knowing

**`fastboot boot` is broken on this device.** It crashes LK with *any* image,
including the phone's own untouched `boot.img`. Only `fastboot flash recovery`
followed by `adb reboot recovery` is a valid test path. Run that positive control
**first** — a dozen careful A/B experiments here were invalidated because it was
checked last.

**Ping is not proof of life.** The RNDIS gadget is configfs/kernel-side and answers
ICMP with *zero* userspace processes running. Trustworthy signals instead:
`Connection refused` on port 22 (IP stack up, no service), an empty
`/var/log/journal` on the rootfs, and no file in the rootfs modified after build time.

**Two MediaTek drivers cannot be disabled via Kconfig.** Both `smb1351-charger` and
`drcc` are built with `obj-y` and the config-gated line commented out:

```makefile
#obj-$(CONFIG_SMB1351_USB_CHARGER) += smb1351-charger.o
obj-y += smb1351-charger.o
```

Changing the config has no effect; the source must be patched.

**`--lax` and `--force` are different pmbootstrap flags.** `--lax` only skips zapping
the buildroot; `--force` is what actually rebuilds. Editing a kernel config without
bumping `pkgrel` yields `Package is up to date` and **nothing is built**. Use
`pmbootstrap build --force --lax`. A real kernel build takes ~6 min with 12–14 `cc1`
processes; finishing in 2 min means it did not build.

**Do not verify a kernel config by grepping the decompressed image** for symbol
names — kallsyms stores them token-compressed, so the search always returns 0.
Compare sha256, or just boot it.

**`pmbootstrap install` mints new filesystem UUIDs on every run**, so a freshly built
`boot.img` will not match an SD card written earlier. Either rewrite the card or
patch the cmdline in the boot header (offset 64, 512 bytes).

**pmOS's default cmdline starts with `quiet`,** which hides every KERN_INFO line.
Replace it with `loglevel=8 ignore_loglevel` before reading any boot log.

**NCM is not available on this kernel** — `CONFIG_USB_CONFIGFS_NCM` is absent, so
`deviceinfo_usb_network_function="ncm"` silently falls back to RNDIS:

```
mkdir: can't create directory '.../functions/ncm.usb0': No such file or directory
```

macOS cannot drive RNDIS; use a Linux host.

---

## Getting a shell inside the initramfs

Add `pmos.debug-shell` to the kernel cmdline. This exposes a **USB ACM serial
device** (`/dev/ttyACM0` on the host), not telnet.

On Ubuntu you must first stop ModemManager, which grabs every new serial device
and causes `Device or resource busy`:

```sh
sudo systemctl mask ModemManager
```

For a shell that survives the *whole* initramfs run including mount failures, add
your own hook to the initramfs instead:

```sh
# hooks/99-telnetd.sh
telnetd -l /bin/sh -p 23 &
```

It dies at `switch_root` — which is itself a useful signal: telnet going from open
to `Connection refused` means `switch_root` succeeded.

[`scripts/pmos-serial-shell.py`](scripts/pmos-serial-shell.py) drives the ACM shell
non-interactively.

---

## Repository layout

```
patches/   kernel source patches (apply via pmaports APKBUILD source=)
scripts/   SD card writer, serial shell helper
logs/      pstore/ramoops captures backing every claim above
docs/      full investigation trace (Vietnamese, chronological)
```

## Hardware notes

- SoC: MediaTek MT6769T (Helio G80), non-A/B, unlocked bootloader
- Panel: `nt36672A_fhdp_dsi_vdo_tianma_j19_lcm_drv` (selected by LK via cmdline)
- Touch: Novatek NT36672 (`CONFIG_TOUCHSCREEN_MTK_NT36672`)
- Charger: SMB1351 over i2c-7 @ 0x55
- USB-C: FUSB303
- SD slot: `msdc1`, works at SDR104

## License

Patches are derived from `LineageOS/android_kernel_xiaomi_mt6768` and inherit
GPL-2.0. Notes and scripts: MIT.
