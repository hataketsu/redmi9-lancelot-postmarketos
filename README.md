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

Status: **kernel boots, display lights up, SD card is detected, initramfs mounts
the rootfs and `switch_root` succeeds.** systemd then freezes; see below.

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
