# Redmi 9 (lancelot) — trace chẩn đoán

Ngày: 2026-08-04. Máy: Xiaomi Redmi 9, codename `lancelot`, MediaTek Helio G80 (MT6768),
non-A/B, bootloader unlock (`verifiedbootstate: orange`), serial `81d4ca960401`.

---

## 1. Triệu chứng ban đầu

Chủ máy mô tả: chạy được ~1 tiếng thì tự reboot; reboot nhiều lần thì thành bootloop
vĩnh viễn. Sau đó bổ sung: hay reboot **đúng lúc mở khoá màn hình**.

Lúc cắm vào máy tính, `adb` báo `unauthorized`.

## 2. Vào được máy

Máy chỉ tin khoá ADB nằm trên server **m416** (`hataketsu@M416`), không tin khoá của Mac
(`hataketsu@mbam415.local`). Không có khoá đó thì `adb` báo `unauthorized` vĩnh viễn, mà
popup chấp nhận thì không bấm được vì máy đang bootloop.

Khoá đã lưu tại `./adbkey` (chmod 600) và `~/.android/vendorkeys/m416-adbkey`.

```bash
export ADB_VENDOR_KEYS=~/.android/vendorkeys/m416-adbkey
adb kill-server   # khoá chỉ nạp lúc khởi động adb server
adb devices
```

Recovery **không** dùng lại khoá này (không mount được `/data` mã hoá) nên luôn phải bấm
Allow trên màn hình.

## 3. Không phải bootloop — là treo ở userspace

Theo dõi 60 giây: `transport_id` trên USB **không đổi**. Máy chưa hề khởi động lại lần nào,
nó dừng ở bước cuối của quá trình boot.

```
sys.boot_completed  = <trống>
init.svc.bootanim   = running
init.svc.zygote     = restarting     ← zygote chết đi chết lại
```

Zygote 32-bit abort khi nạp ART boot image:

```
Abort message: 'Check failed: decompressed_size == image_size_
                (decompressed_size=1988263, image_size_=2013772)'
```

Thiếu 25.509 byte khi giải nén một block. Thêm một file hỏng độc lập:

```
CANNOT LINK EXECUTABLE "/system/bin/gpuservice":
  "/system/lib64/libgpuservice.so" has bad ELF magic: 02e4006f
```

16 byte đầu file đó là **code ARM64 nằm sai vị trí** (`e0 03 1f 2a` = `mov w0, wzr`), không
phải rác ngẫu nhiên — dấu hiệu lệch block khi ghi.

`dm-verity` tắt (bình thường với bootloader unlock) nên block hỏng lọt qua im lặng thay vì
báo I/O error, đó là lý do máy boot được tới tận zygote rồi mới chết.

> ⚠️ **Mục 4 dưới đây SAI. Kết luận đúng ở mục 13.** eMMC đã hết tuổi thọ
> (`life_time = 0x0b 0x0b`). Giữ lại nguyên văn để thấy suy luận sai ở đâu.

## 4. Loại trừ hỏng eMMC — KẾT LUẬN SAI

- Đọc lại cùng file 3 lần → MD5 giống hệt nhau ⇒ hỏng cố định trên flash, không phải lỗi
  đọc ngẫu nhiên của RAM/controller.
- `dmesg` (có root): **không** `mmc error`, **không** `I/O error`, **không**
  `blk_update_request`, **không** `F2FS/EXT4-fs error`.
- `thermal_pcba is 28` — 28°C, không quá nhiệt.

Kết luận: chip nhớ khoẻ. Hỏng do **một lần ghi bị ngắt giữa chừng**, nhiều khả năng là OTA
nightly đang ghi thì máy bị reset cứng.

## 5. Dữ liệu

`/data` là f2fs 19G, mới dùng 15%, còn nguyên. Nhưng FBE bật, khoá CE dẫn xuất từ PIN:

```
$ ls /data/media/0
1ZcZhDAAAAQvRDyWGLROAIiDMvVU2EY2
60MUsBAAAAQJyPemAHhZ+ivp9XBVr1rH
```

Tên file mã hoá. Root cũng không mở được — phải boot tới màn khoá và nhập PIN. Chủ máy
quyết định **không cần giữ data**, nên bỏ qua.

## 6. Tìm ROM

LineageOS đã **ngưng hỗ trợ** lancelot. API build trả `[]`, thư mục mirror `full/lancelot/`
tồn tại nhưng rỗng, mọi file 404. Bản `20241012` đang cài và bản cuối `20241228` đều không
còn tải được.

Bản dùng được: `lineage-21.0-20240610-UNOFFICIAL-lancelott.zip` (chú ý tên **hai chữ `t`**;
bản một `t` trả 404). Chỉ host `master.dl.sourceforge.net` cho tải, các host SourceForge
khác đều 403 với curl.

```
sha256 12609804750cba3c1d5a5a01dee08a0838fc687e7249235d957b935a65ec209d
size   1071582726
```

Hash khớp với file `.sha256sum` chính chủ ⇒ file đổi tên chứ không hỏng.

Gói chứa sẵn `recovery.img` ký cùng khoá, nên tránh được lỗi `signature verification failed`
mà Lineage Recovery 20 chính thức sẽ báo với gói unofficial.

```
pre-device     = lancelot,galahad,shiva
post-sdk-level = 34 (Android 14)
ota-type       = BLOCK (non-A/B)
```

## 7. Cài lại

```bash
adb reboot bootloader
fastboot flash recovery rom/imgs/recovery.img
fastboot reboot recovery
# recovery: Factory reset → Format data  (bắt buộc: khoá ký khác, data cũ không giải mã được)
# recovery: Apply update → Apply from ADB
adb sideload rom/lineage-21.0-20240610-UNOFFICIAL-lancelott.zip
```

Kết quả: máy boot lên.

```
sys.boot_completed = 1
init.svc.zygote    = running
ro.lineage.version = 21.0-20240610-UNOFFICIAL-lancelot
```

Quét lại 1433 file ELF trên `/system`: **0 file hỏng**. (`/system/bin/monkey` bị gắn cờ là
báo nhầm — shell script mở đầu bằng `# Script...`, không phải ELF.)

## 8. Lỗi gốc: watchdog reset khi đánh thức

Sau khi cài lại, lỗi **vẫn còn**. Bắt được một lần crash trực tiếp:

```
ro.boot.bootreason = Watchdog        ← chữ hoa, khác 'wdt' viết thường của reboot phần mềm
sys.boot.reason    = watchdog
console-ramoops    = 262132 byte     (bình thường 96988)
```

Kernel ngừng đáp ứng, phần cứng đếm hết giờ và cưỡng bức reset — nên không kịp ghi gì qua
Android.

### Cơ chế

```
[1164.163197] fusb303 7-0021: fusb303_suspend: enter
[1164.165152] dpm_run_callback(): platform_pm_suspend+0x0/0x54 returns -16
[1164.165190] PM: Device alarmtimer failed to suspend: error -16
[1164.165219] PM: Some devices failed to suspend, or early wake event detected
[1164.166155] fusb303 7-0021: fusb303_resume: enter
```

`-16` = `-EBUSY`. `alarmtimer_suspend()` trả `-EBUSY` khi có báo thức RTC sẽ nổ sớm hơn
ngưỡng tối thiểu 2 giây. Lặp ở giây 1164, 1173, 1177, 1183, 1186, xen kẽ với:

```
Freezing of tasks aborted after 0.007 seconds
```

Máy quần liên tục giữa ngủ và thức, không bao giờ ngủ sâu được — **suspend/resume thrashing**.

### Dòng thời gian lần chết

```
1007–1111  chu kỳ suspend/resume ngắn, cách đều 6.6s
1164–1186  năm lần suspend thất bại, alarmtimer -EBUSY
   ~1238   bấm nút nguồn; "Ignoring screen off event ... for reason power_button"
           "Unblocked screen on after 2003 ms"        ← màn hình 2 giây mới bật
   ~1247   SurfaceSyncGroup(NotificationShade) quá hạn 1000 ms, hai lần
   1253.3  log dứt — watchdog reset
```

`NotificationShade` là lớp giao diện của màn khoá/bảng thông báo — đúng thứ đang thao tác.

### Mức độ chắc chắn

- **Chắc**: watchdog reset thật; suspend liên tục thất bại vì `alarmtimer -EBUSY`; đường
  display treo lúc bật màn (2003 ms + SurfaceSyncGroup timeout).
- **Chưa chứng minh**: liên hệ nhân quả giữa hai thứ đó. `alarmtimer -EBUSY` tự nó thường
  vô hại, hậu quả bình thường chỉ là tốn pin.

## 8b. Đo trực tiếp: máy không bao giờ ngủ sâu

Kernel tự khai bằng bộ đếm riêng:

```
/sys/power/suspend_stats/
  success          228        fail  71
  last_failed_dev  alarmtimer
  last_failed_step freeze
```

Ép Doze khi đã rút cáp (`AC powered: false`, `USB powered: false`), mọi Suspend Blocker
`ref count=0`, `mWakefulness=Asleep`. Đo trong 75 giây không đụng adb:

```
suspend thành công +86   thất bại +25   →  111 lần thử / 75s ≈ 1.5 lần mỗi giây
```

Máy ngủ rồi bị dựng dậy ngay, liên tục. Máy khoẻ thì suspend một lần và nằm im hàng phút.
CPU vẫn rảnh 88% (`/proc/uptime` = 1020.22 / 7222.28 idle, 8 nhân).

Nguồn đánh thức, kernel ghi rõ:

```
PM: Pending Wakeup Sources: ttyC0
Abort: Pending Wakeup Sources: ttyC0
PM: Last active Wakeup Source: bat_percent_notify_lock wakelock
[SPM] suspend wake up by R12_SYS_TIMER_EVENT_B, timer_out = 1016 / 308 / 345 / 190 / 29
Resume caused by IRQ 238, SPM
```

`ttyC0` = cổng serial CCCI, đường nói chuyện với modem.

**Báo thức KHÔNG phải do app.** `dumpsys alarm`: 26 pending, top là
`com.android.providers.calendar` với 2 wakeups, `com.android.networkstack` 1 wakeup. Quá ít.
Vấn đề nằm ở tầng kernel/driver RTC, không phải ứng dụng.

## 8c. Crash lần 2 — loại trừ modem

Bật airplane mode (modem tắt, `ttyC0` từ đầy rẫy xuống còn 1 lần trong log), **vẫn crash**:

```
ro.boot.bootreason = Watchdog
airplane_mode_on   = 1
```

⇒ **Modem không phải thủ phạm.** Giả thuyết modem bị bác bỏ.

Log lần 2 kết thúc ở giây 176.8 giữa lúc driver sạc polling, không có hoạt động suspend gần
đó. Phía Android:

```
AudioALSAHardware -setParameters(): screen_state=off
BL=   0, ESS= 256,
HWUI  dequeueBuffer failed, error = -110; switching to fallback
```

`-110` = `-ETIMEDOUT`. SurfaceFlinger không lấy được buffer từ driver hiển thị.

### Mẫu số chung của cả hai lần

```
crash1:  SurfaceSyncGroup(NotificationShade) timeout 1000ms + "Unblocked screen on after 2003 ms"
crash2:  HWUI dequeueBuffer failed, error = -110 (ETIMEDOUT)
```

Cả hai đều là **đường hiển thị treo đúng lúc màn hình chuyển trạng thái bật/tắt**.
`alarmtimer -EBUSY` giờ trông giống hậu quả hoặc nhiễu độc lập hơn là nguyên nhân.

### Panel — đã loại trừ

```
LCM_name = nt36672A_fhdp_dsi_vdo_tianma_j19_lcm_drv     (từ cmdline, bootloader dò)

[41.53] [KERNEL/LCM][nt36672A] lcm_suspend enter  → [41.68] exit
[60.47] [KERNEL/LCM][nt36672A] lcm_resume_power enter → [60.65] lcm_resume exit
```

Driver LCM chạy suspend/resume trọn vẹn, không lỗi. `lancelot_defconfig` liệt kê 4 loại panel
(tianma/huaxing/dijing) nên giả thuyết "chọn nhầm panel" là hợp lý, nhưng **bằng chứng không
ủng hộ**. Chỗ treo nằm phía trên driver panel — tầng SurfaceFlinger/HWC.

### Trạng thái nghi vấn

| Nghi phạm | Kết luận |
|---|---|
| eMMC hỏng | **Loại** — không lỗi mmc/IO, MD5 ổn định qua nhiều lần đọc |
| Pin chai | **Loại** — sạc chậm là do cắm cổng USB laptop (~500mA) |
| Modem / ttyC0 | **Loại** — crash tái hiện khi airplane mode bật |
| Chọn nhầm panel LCM | **Không ủng hộ** — driver suspend/resume sạch |
| `alarmtimer -EBUSY` | Có thật, nhưng nhiều khả năng là hậu quả |
| **Đường display/HWC treo** | **Nghi phạm chính** — cả 2 lần crash đều timeout ở đây |

### Việc chưa làm

- Truy vì sao SurfaceFlinger/HWC treo lúc đổi trạng thái màn hình.
- Lưu ý: đây là bản **UNOFFICIAL** LineageOS 21. Thượng nguồn chỉ có kernel
  (`android_kernel_xiaomi_mt6768`) và blob (`TheMuppets/proprietary_vendor_xiaomi_lancelot`)
  ở nhánh **lineage-20**, không có cho 21 — nên bản 21 này chắc chắn dùng kernel/blob tự port.
  Lỗi display trong một bản port như vậy là hoàn toàn khả dĩ.
- **Khuyến nghị**: dựng hoặc tìm bản **LineageOS 20**, phiên bản có đủ bộ thượng nguồn chính
  thống, cũng là bản máy chạy trước đây. Nếu lỗi là bug của bản port 21 thì cách này giải quyết.

## 9. Nhiễu trong log — đọc log nhớ trừ ra

- `dump_regs`: **2821 dòng** trong vòng đệm 256 KB, chiếm gần trọn. Là driver sạc polling
  ~1 cụm/5 giây trong bản debug. **Không** phải printk storm (chỉ 6 dòng/giây), **không**
  phải nguyên nhân — nhưng nó đẩy hết lịch sử log ra ngoài, làm mất luôn dấu vết watchdog.
- `mtk_qmax_agin:9999999 qmax:5020000`: fuel gauge, spam liên tục, vô hại.
- `dhx--state:N--current now = ±...`: dòng điện nhảy ±2.3 A, kèm `set otg current 1.8A` 46
  lần. **Chưa giải thích được.** Cắm cổng USB laptop thì không thể sạc 2.3 A.
- `load average` 26–28 lúc máy rảnh: **ảo**. 25 kernel thread MediaTek (`[wdtk-*]`,
  `[battery_thread]`, `[disp_*]`, `[ccci_*]`…) nằm ngủ uninterruptible theo thiết kế, bị
  đếm vào load. PSI xác nhận máy rảnh: `io some avg10=0.00`, `cpu some avg10=1.15`.
  ⚠️ Đừng dùng load average trên máy này làm bằng chứng gì cả.

## 10. Cấu hình đã đặt trên máy

```bash
# tắt phantom process killer — Android 12+ giết ngầm sshd/tmux chạy dài
settings put global settings_enable_monitor_phantom_procs false
device_config put activity_manager max_phantom_processes 2147483647

# adb qua wifi
adb tcpip 5555 && adb connect 192.168.1.200:5555

# giảm nhiễu ramoops (tạm, mất sau reboot) — dump_regs ở mức ≤4 nên mức 3 sẽ chặn
echo 3 4 1 7 > /proc/sys/kernel/printk
```

`hung_task_timeout_secs` **không có** — kernel không bật `CONFIG_DETECT_HUNG_TASK`.

## 11. Nội dung thư mục

```
rom/lineage-21.0-20240610-UNOFFICIAL-lancelott.zip   ROM, hash đã kiểm
rom/SHA256SUMS                                        shasum -a 256 -c SHA256SUMS
rom/imgs/{boot,recovery,dtbo,vbmeta,vbmeta_system,vbmeta_vendor}.img
logs/bootloop-original/     log lúc còn bootloop (crash.log, main.log, ramoops, last_kmsg)
logs/crash1-watchdog/       log lần watchdog reset bắt trực tiếp — quan trọng nhất
adbkey, adbkey.pub          khoá ADB máy này tin (từ m416)
```

Bản sao dự phòng của ROM và imgs nằm trên **ctdagent** tại `~/rom/`.

## 12. Bước tiếp

1. `dumpsys alarm` — tìm thủ phạm đặt báo thức dày (việc dở dang).
2. Thử chạy **không cắm cáp** nhiều lần đánh thức, để tách đường USB/sạc ra khỏi nghi vấn.
3. Mỗi lần reboot: kéo `/sys/fs/pstore/console-ramoops` **ngay**, buffer chỉ giữ lần gần nhất.
4. Cài Termux (`termux-app_v0.118.3+github-debug_arm64-v8a.apk`) — mục tiêu dùng máy làm
   console/hackpad, Claude Code chạy trên ctdagent, máy chỉ là terminal + tmux.
5. postmarketOS: **chưa có port** cho lancelot. Gần nhất là `xiaomi-merlin` (hạng `testing`),
   build từ **cùng** repo `LineageOS/android_kernel_xiaomi_mt6768`, và `lancelot_defconfig`
   có sẵn trong đó. Cảm ứng dùng `CONFIG_TOUCHSCREEN_MTK_NT36672` (merlin dùng nhánh driver
   khác: `NT36xxx_HOSTDL_SPI`). Muốn thử an toàn thì cần **thẻ microSD** để rootfs không
   đụng `userdata`; boot bằng `fastboot boot` (không ghi gì) hoặc flash vào partition
   `recovery` 64 MB làm khe thứ hai — hoàn tác bằng `fastboot flash recovery`.
```

---

# 13. KẾT LUẬN CUỐI — eMMC hết tuổi thọ

Chủ máy cho biết lỗi này **đã có từ trước** trên:

- **LineageOS 20** (chính thức, đủ bộ thượng nguồn)
- **MIUI** (ROM gốc hãng) — và trên MIUI, sau khi reboot thì **báo lỗi dm-verity**

Ba nền phần mềm độc lập, cùng một lỗi ⇒ nguyên nhân nằm **dưới** mọi ROM.

## Bằng chứng quyết định

```
/sys/block/mmcblk0/device/life_time     = 0x0b 0x0b
/sys/block/mmcblk0/device/pre_eol_info  = 0x01
name = DD68MB   manfid = 0x15   rev = 0x8
```

Theo JEDEC eMMC, `DEVICE_LIFE_TIME_EST_TYP_A/B` chạy `0x01` (0–10% tuổi thọ đã dùng) tới
`0x0A` (90–100%). **`0x0B` = đã vượt quá tuổi thọ ước tính tối đa.**

Cả `TYP_A` (vùng SLC) lẫn `TYP_B` (vùng MLC) đều `0x0B`. **Chip nhớ đã hết đời.**

`pre_eol_info = 0x01` (Normal) trông mâu thuẫn nhưng không phải: `life_time` đo theo số chu kỳ
xoá so với định mức, `pre_eol_info` đo theo lượng khối dự phòng đã tiêu. Vượt định mức chu kỳ
mà vẫn còn khối dự phòng là chuyện bình thường.

## Mọi triệu chứng khớp vào một nguyên nhân

| Quan sát | Giải thích |
|---|---|
| `/system` hỏng ELF magic, ART image thiếu byte | eMMC ghi/đọc sai lệch âm thầm |
| MIUI báo lỗi dm-verity sau reboot | verity **bắt được** sai lệch đó |
| LineageOS bootloop âm thầm | verity tắt (bootloader unlock) → lọt qua |
| watchdog reset lúc bật/tắt màn hình | đọc block treo → tiến trình kẹt D-state → `dequeueBuffer` ETIMEDOUT → hệ thống đứng |
| xảy ra trên MIUI + Lineage 20 + Lineage 21 | nguyên nhân nằm dưới tầng ROM |

## Sai lầm trong quá trình chẩn đoán — rút kinh nghiệm

Mục 4 kết luận "eMMC khoẻ" dựa trên hai bằng chứng **quá yếu**:

1. *"Không thấy lỗi mmc trong dmesg"* — dmesg chỉ phủ một cửa sổ thời gian ngắn.
2. *"MD5 đọc lại 3 lần ổn định"* — chỉ chứng minh file **đã hỏng sẵn** thì đọc ra vẫn nhất
   quán. Không nói gì về sức khoẻ chip.

**Lẽ ra phải đọc `/sys/block/mmcblk0/device/life_time` và `pre_eol_info` ngay từ đầu** — một
lệnh, trả lời trực tiếp, không cần suy luận gián tiếp. Đây là việc đầu tiên nên làm với bất kỳ
máy Android nào nghi hỏng lưu trữ.

## Hệ quả

- **Không sửa được bằng phần mềm.** Flash ROM nào cũng vô ích.
- **Không đáng sửa phần cứng.** eMMC hàn BGA, thay phải đóng bi lại chip.
- **postmarketOS cũng không cứu được** — đổi hệ điều hành không làm chip nhớ trẻ lại.
- Đừng dựng LineageOS 20 nữa: chủ máy đã chạy bản đó và vẫn hỏng.

## Lối đi còn lại cho mục đích console/hackpad

Chạy hệ thống **trên thẻ microSD**, để eMMC gần như không phải làm gì:

- rootfs, log, mọi thứ ghi xuống thẻ
- eMMC chỉ còn giữ partition `boot` (nhỏ, chỉ đọc, ít bị hành nhất)

Máy sẽ không bao giờ đáng tin để làm điện thoại chính, nhưng làm hackpad chạy SSH thì vẫn khả
thi — với điều kiện chấp nhận nó có thể chết bất cứ lúc nào.

---

# 14. postmarketOS — da build xong, cho test boot

Muc tieu: chay he thong tu **the microSD**, eMMC (da hong, xem muc 13) khong bi ghi gi.

## Vi sao cach nay chay duoc con Android thi khong

Android buoc phai nap `/system`, `/vendor`, `/product` tu partition `super` tren eMMC:

```
androidboot.boot_devices = bootdevice,11230000.mmc      ← chi mot controller eMMC
root                     = /dev/ram
/dev/block/by-name/super → /dev/block/mmcblk0p43
/dev/block/platform/bootdevice/  → chi co mmcblk0*
```

`ueventd` chi tao `by-name` cho controller do; khe the la `msdc1`, dia chi khac, **vinh vien
khong co `by-name`**. init cua Android khong co cach goi ten partition tren the.

pmOS thi initramfs quet tim partition **theo nhan** (`pmOS_boot` / `pmOS_root`) tren moi block
device, ke ca `mmcblk1`. Nen rootfs nam tren the van tim ra.

Bootloader va kernel **van phai** nam tren eMMC voi moi he dieu hanh — khong tranh duoc.
Nhung dung `fastboot boot` thi kernel nap thang vao RAM, khong ghi partition nao.

## Da lam

Build tren **ctdagent** (16 nhan, Ubuntu 24.04, KVM nen chroot chay duoc):

```
pmbootstrap 3.11.1   (git — PyPI da yank het cac ban)
   ~/pmbootstrap                          ma nguon
   ~/.local/var/pmbootstrap               workdir + pmaports
```

Port `xiaomi-merlin` (Redmi Note 9) nam o **`device/archived/`** tren nhanh `main` — port da bi
bo, khong ai duy tri. (Truoc do tra qua GitLab API voi `ref=master` thay o `testing` — nhanh do
da cu.) Da copy sang `device/testing/` de build.

Dung merlin nguyen ban vi cung SoC MT6768, cung dtb `mediatek/mt6768`, va offset boot image
**trung khit** lancelot — kiem chung bang `pmbootstrap bootimg_analyze` tren chinh `boot.img`
cua LineageOS:

```
flash_offset_base 0x40078000   kernel 0x00008000   ramdisk 0x07c08000
flash_offset_dtb  0x0bc08000   tags   0x0bc08000   second  0xbff88000
pagesize 2048   header_version 2
```

Ket qua build:

```
linux-xiaomi-merlin-4.14.320-r0.apk     14 MB
pmos-boot-android.img                   25 MB   Android bootimg, kernel@0x40080000
xiaomi-merlin-boot.img.gz               52 MB   ext2, label pmOS_boot  (512 MiB bung ra)
xiaomi-merlin-root.img.gz              200 MB   ext4, label pmOS_root  (754 MiB bung ra)
```

UI = `console`, service manager = systemd, mat khau user = `147147`.

Tat ca o `pmos/`, checksum trong `pmos/SHA256SUMS`.

## Cach test (chua lam — can mat khau sudo)

```bash
cd ~/Projects/redmi9/pmos
sudo ./flash-sdcard.sh          # hoi chon the, go "XOA" de xac nhan
```

Script tu kiem tra: o phai thao roi duoc, < 128GB, > 4GB — tranh dd nham o cung.
Tao 2 phan vung (600M + phan con lai) roi ghi de anh ext2/ext4 len.

Roi tren dien thoai:

```bash
# cam the vao may, tat han, giu Vol Down + Nguon
fastboot devices
fastboot boot pmos-boot-android.img     # nap RAM, KHONG ghi eMMC
```

Hong thi rut pin bat lai → LineageOS nguyen ven. Len duoc thi `ssh user@172.16.42.1`.

## Ky vong that

Day la kernel cua **Redmi Note 9** chay tren **Redmi 9**. Co so ky thuat co that (cung SoC,
cung dtb, offset trung) nhung van la canh bac. Ba ket qua co the:

1. Man hinh den, khong gi ca — kernel khong boot
2. Len console khung hinh tho — thanh cong
3. Len nhung khong co man hinh, vao duoc qua USB (`172.16.42.1`) — thanh cong mot phan

Ca ba deu cho thong tin. Neu (2) hoac (3), buoc sau la tao port `lancelot` rieng:
`lancelot_defconfig` co san trong cung repo kernel, va cam ung dung nhanh driver khac
(`CONFIG_TOUCHSCREEN_MTK_NT36672` thay vi `NT36xxx_HOSTDL_SPI` cua merlin).

---

# 15. postmarketOS — tien trinh thuc te (phien 2026-08-04, buoi chieu)

## 15.1 SAI LAM PHUONG PHAP QUAN TRONG NHAT

Chay hang loat phep thu so sanh anh boot **ma khong co doi chung duong**. Sau chuc lan thu
moi phat hien ra:

```
fastboot boot rom/imgs/boot.img        (chinh anh LineageOS dang chay tot, khong sua gi)
=> ro.boot.bootreason = lk_crash
```

**`fastboot boot` HONG tren may nay — crash voi MOI anh, ke ca anh hoan hao.**

Moi ket luan rut ra tu cac phep thu qua `fastboot boot` deu **vo gia tri**: gia thuyet DTB noi
thua, gia thuyet kich thuoc anh, gia thuyet binary kernel. Tat ca deu phai huy.

**Bai hoc: chay doi chung duong TRUOC khi chay bat ky phep thu so sanh nao.**

Duong thu nghiem dung duy nhat: **flash vao partition `recovery` roi `adb reboot recovery`**.

## 15.2 Nguyen nhan `lk_crash` that su: THIEU AVB

Anh LineageOS co cau truc Android Verified Boot; anh pmbootstrap tao ra thi khong:

```
AVB0  offset 16,117,760   vbmeta header, ngay sau noi dung anh boot
      16,118,023..439     descriptors
AVBf  offset 67,108,800   footer, 64 byte cuoi partition 64 MB

Footer version 1.0   Image size 67108864   VBMeta size 704   Algorithm: NONE
```

LK doc cau truc nay ke ca khi bootloader da unlock; thieu la crash.

**Cach sua:**

```bash
python3 avbtool.py add_hash_footer --image <boot.img> \
  --partition_name recovery --partition_size 67108864 --algorithm NONE
```

`avbtool.py` lay tu AOSP (nho `base64 -D` tren macOS, khong phai `-d`):
`https://android.googlesource.com/platform/external/avb/+/refs/heads/main/avbtool.py?format=TEXT`

Sau khi them AVB: `lk_crash` **bien mat**, kernel pmOS bat dau chay.

## 15.3 Kernel panic: smb1351 NULL deref

```
[27.715] Unable to handle kernel NULL pointer dereference at virtual address 00000020
Call trace:
  smb1351_float_chg_det_work+0x3c/0x138
```

Kich hoat dung luc cam cap USB (`apsd_update_work: chg_type: 1` -> `is device` -> oops).

Nguon: `drivers/power/supply/mediatek/charger/smb1351-charger.c`

```c
3043:  chip->chg_consumer = charger_manager_get_by_name(chip->dev, "charger_port1");
3045:  if (!chip->chg_consumer) {
3046:      pr_info("get charger consumer device failed\n");   // chi canh bao roi DI TIEP
3048:  }
...
1326:  struct charger_manager *cm = chip->chg_consumer->cm;   // dung thang -> NULL deref
2617:  struct charger_manager *cm = chip->chg_consumer->cm;   // cho thu hai
```

⚠️ **Tat `CONFIG_SMB1351_USB_CHARGER` KHONG co tac dung.** Makefile bo qua bien config:

```makefile
41: #obj-$(CONFIG_SMB1351_USB_CHARGER) += smb1351-charger.o
42: obj-y += smb1351-charger.o          ← build vo dieu kien
```

**Cach sua:** patch `smb1351-null-guard.patch` (da nam trong pmaports tren ctdagent), doi
initializer sang ternary + guard `if (!cm) return;`. Luu y kieu tra ve khac nhau giua hai ham
(`void` va `int`), va khai bao phai dat truoc lenh.

Sau patch: oops **bien mat hoan toan**.

## 15.4 Trang thai hien tai — kernel chay, chua toi userspace

Log day du (205 KB, 3178 dong, 0.000 -> 30.015s) cho thay:

```
[0.000000] Linux version 4.14.320 (pmos@ctdagent) ... #1-postmarketOS
[0.000897] console [tty0] enabled
[0.252487] Trying to unpack rootfs image as initramfs...
[0.587731] Freeing initrd memory: 11424K          ← initramfs GIAI NEN OK (11.4 MB)
[0.111223] mtk_wdt_init ok                        ← watchdog driver co nap
[6.473686] mmc1: new ultra high speed SDR104 SDHC card at address aaaa
[6.473970] mmcblk1: mmc1:aaaa SC32G 29.7 GiB
[6.476356]  mmcblk1: p1 p2                        ← THE NHO NHAN DUOC, ca 2 phan vung
...
[30.015393] (log dut)  -> bootreason = Watchdog
```

**Da chay duoc:** kernel boot, console, initramfs giai nen, the microSD nhan dien day du.
**Chua toi:** `Freeing unused kernel memory` / `Run /init` — userspace chua khoi dong sau 30s.
LineageOS len userspace trong ~10s.

Khong co khoang treo don le nao dang ke (chi 2.6s va 3.2s), tuc khong ket o mot driver — ma
toan bo qua trinh khoi tao qua dai, roi watchdog phan cung nổ.

`CONFIG_MTK_WD_KICKER=y` **da bat** trong config pmOS (lancelot_defconfig con khong co).

Man hinh: chu may bao thay **mot vet xanh o dinh man hinh** roi reboot — framebuffer co hoat
dong, panel duoc khoi tao.

## 15.5 Bay can biet

**UUID doi moi lan `pmbootstrap install`.** Anh boot ghi `pmos_boot_uuid`/`pmos_root_uuid` vao
cmdline; the nho giu UUID cua lan build truoc => khong khop, initramfs khong tim ra rootfs.
Hoac ghi lai the, hoac sua cmdline trong header anh boot (offset 64, dai 512 byte).

UUID hien co tren the: boot `3d0f04bd-e1b6-4a44-b70b-75066c1fe718`,
root `cf36166f-097e-4d65-9e69-f5c01a01278d`.

**`quiet` trong cmdline pmOS che het thong diep KERN_INFO.** Bo `quiet splash plymouth.*`,
them `loglevel=8 ignore_loglevel` moi thay duoc gi.

**LK noi them cmdline cua no** vao truoc/sau cmdline trong anh — ca hai deu ton tai.

## 15.6 Buoc tiep

1. Tim vi sao khoi tao driver mat > 30s. So sanh dong thoi gian voi log LineageOS.
2. Hoac keo dai/tat watchdog phan cung de kernel co du thoi gian toi userspace.
3. Luu y: **may nay tu no da bi Watchdog reset ngay tren LineageOS** (muc 8, 13). Khong loai
   tru phan reset 30s nay co phan dong gop cua chinh loi phan cung eMMC.

## 15.7 File

```
pmos/boot-v4-verbose.img     ban moi nhat: patch smb1351 + cmdline verbose + UUID dung the
pmos/boot-v4-avb.img         ban tren + AVB footer, san sang fastboot flash recovery
pmos/avbtool.py              cong cu AVB tu AOSP
logs/pmos-boot-fail/         lan dau, chua co AVB
logs/pmos-avb-try/           co AVB, crash smb1351
logs/pmos-v2/, pmos-v3/      cac buoc trung gian
logs/pmos-v4/console-ramoops 205 KB, log day du nhat — tai lieu tham chieu chinh
```

Tren ctdagent: `~/pmbootstrap`, `~/.local/var/pmbootstrap`, patch nam trong
`pmaports/device/testing/linux-xiaomi-merlin/smb1351-null-guard.patch`.

---

# 16. postmarketOS BOOT DUOC — 2026-08-04

```
USB Serial Number = "postmarketOS"
USB Product Name  = "Xiaomi Redmi Note 9"
idVendor 0x18D1   idProduct 0xD001
```

Chay on dinh > 12 phut, khong watchdog reset.

## Bon rao can, theo thu tu phat hien

| # | Trieu chung | Nguyen nhan | Cach go |
|---|---|---|---|
| 1 | `lk_crash` voi MOI anh | Thieu **AVB footer** | `avbtool add_hash_footer --partition_name recovery --partition_size 67108864 --algorithm NONE` |
| 2 | Oops luc cam cap USB, ~27s | `smb1351-charger.c` deref `chg_consumer` NULL | patch `smb1351-null-guard.patch` |
| 3 | Khong bao gio toi `/init`, watchdog reset ~30s | **`drcc_init` treo, khong tra ve** | patch `drcc-skip-init.patch` (`return 0` dau ham) |
| 4 | Khong doc duoc log | `quiet` trong cmdline che het KERN_INFO | thay bang `loglevel=8 ignore_loglevel` |

## Rao can 3 — cach tim ra

Them `initcall_debug` vao cmdline. Log cho ngay:

```
[0.943525] calling  deferred_probe_initcall+0x0/0x44 @ 1
[0.949224] initcall deferred_probe_initcall+0x0/0x44 returned 0 after 5550 usecs
[0.949239] calling  drcc_init+0x0/0xdc @ 1
                                             ← KHONG CO dong "returned"
```

`drcc_init` la initcall cuoi cung duoc goi, khong bao gio tra ve. Nguon:
`drivers/misc/mediatek/base/power/drcc_v1/mt6768/mtk_drcc.c:1389`, dang `late_initcall`.
Treo trong `create_procfs()` hoac `drcc_probe()` (goi tu `platform_driver_register`).
DRCC chi la toi uu bu dien ap CPU, bo qua duoc.

⚠️ Giong smb1351: **khong co bien Kconfig nao tat duoc**, build vo dieu kien.

## So sanh timeline, cach doc dung

```
moc                  LineageOS      pmOS
ion_init                  0.25      0.24
touch NVT init            0.52      0.77
smb1351 delay_init        0.80      1.02
chg_type detect          10.42     26.67
```

0–1s hai ben nhu nhau. Nhung mat do dong theo cua so 2 giay moi lo ra van de that:

```
LineageOS  2-4s : libprocessgroup ...        ← USERSPACE da chay tu giay thu 2
pmOS       2-30s: chi smb1351 polling        ← kernel dung im, khong lam gi
```

Ket luan ban dau "khoi tao driver qua cham" la **sai**. Kernel dung xong trong 2 giay roi
**dung lai**, khong phai cham.

## Con lai

USB gadget mac dinh cua pmOS la **RNDIS** (`0x18D1:0xD001`) — macOS khong co driver, nen
khong co `172.16.42.1` de SSH. Da them vao `device-xiaomi-merlin/deviceinfo`:

```
deviceinfo_usb_network_function="ncm"
```

macOS ho tro NCM san. Anh moi: `pmos/boot-v7-avb.img`.

Man hinh: den (truoc do co vet xanh + text nhoe khi console kernel ve ra framebuffer).

## Toi uu thoi gian build

pmbootstrap **xoa sach buildroot truoc moi lan build** o che do mac dinh:

```
Zapping buildroots (running in strict mode by default, use --lax to skip zap)
```

Dung `pmbootstrap build --lax` de giu ccache va object trung gian. Doi mot file thi chi bien
dich lai file do thay vi ca kernel (~4 phut).

Doi `deviceinfo` thi **khong** can build lai kernel, chi `install` (~2 phut).

---

# 17. NGUYEN NHAN THAT SU: systemd dong bang vi thieu CONFIG_FHANDLE

Bat duoc bang ramoops sau khi cho pmOS chay tu nhien roi ep reboot sang LineageOS:

```
[ 1.357419] Freeing unused kernel memory: 4544K          ← kernel VAO USERSPACE
[ 1.422904] [pmOS-rd]:   ❬❬ PMOS STAGE 1 ❭❭
[ 1.422949] [pmOS-rd]:   ❬❬ PMOS STAGE 2 ❭❭
[ 7.039585] [pmOS-rd]: Mount root partition (/dev/mmcblk1p2) to /sysroot (read-write)
[ 7.228224] systemd[1]: Failed to determine whether /proc is a mount point: No error information
[ 7.228276] systemd[1]: Failed to determine whether /sys is a mount point: No error information
[ 7.228298] systemd[1]: Failed to determine whether /dev is a mount point: No error information
[ 7.236607] systemd[1]: Freezing execution.
```

**Mount rootfs OK. switch_root OK. systemd len PID 1 roi TU DONG BANG o giay thu 7.**

Nguyen nhan: systemd dung `name_to_handle_at()` de kiem tra mount point. Syscall do can
`CONFIG_FHANDLE`. Kiem tra config:

```
# CONFIG_FHANDLE is not set          ← THIEU
CONFIG_CGROUPS=y  CONFIG_INOTIFY_USER=y  CONFIG_SIGNALFD=y  CONFIG_TIMERFD=y
CONFIG_EPOLL=y    CONFIG_DEVTMPFS=y      CONFIG_SECCOMP_FILTER=y      ← tat ca deu co
```

Thieu dung mot cai. `ENOSYS` tra ve, musl in ra chuoi vo nghia "No error information".

Goc sau hon: luc `pmbootstrap init` de mac dinh, no chon **systemd**
(*"Based on your UI selection, 'default' will result in choosing systemd"*).
systemd 261 chay tren kernel downstream 4.14 nam 2017. **OpenRC** la lua chon dung cho kernel cu.

## Cach suy luan SAI da dung suot buoi

**"ping 172.16.42.1 thong" KHONG chung minh userspace song.** Gadget RNDIS dung configfs, nam
trong kernel, tu tra loi ICMP ke ca khi **khong co mot tien trinh userspace nao**. Moi lan
thay ping ok roi ket luan "he thong dang chay" deu vo can cu.

Dau hieu dung de phan biet:
- `Connection refused` tren cong 22 = tang IP song, khong co dich vu
- Journal rong trong `/var/log/journal` tren the = systemd chua tung chay
- Khong file nao trong rootfs bi ghi sau luc build = he thong that chua tung chay

## Cach lay shell trong initramfs (da kiem chung)

1. cmdline them `pmos.debug-shell` → tao `/dev/ttyACM0` phia host
2. **`sudo systemctl mask ModemManager`** — neu khong se bao `Device or resource busy`,
   ModemManager tu do moi thiet bi serial moi va giu cong
3. Hoac tu them hook ton tai lau hon:
   ```sh
   # hooks/99-telnetd.sh trong initramfs
   telnetd -l /bin/sh -p 23 &
   ```
   Hook nay song xuyen suot initramfs, ke ca khi mount that bai — nhung **chet khi
   switch_root** vi cay tien trinh bi thay the. Chinh dieu do lai la phep thu tot:
   telnet mo roi chuyen sang `Connection refused` = switch_root THANH CONG.

## Bay khi build lai kernel

`--lax` va `--force` lam viec KHAC NHAU:
- `--lax` chi bo buoc zap buildroot (giu ccache, nhanh hon)
- `--force` moi ep build lai

Sua config ma khong bump `pkgrel` thi pmbootstrap bao *"Package is up to date"* va **khong build gi**.
Phai dung **ca hai**: `pmbootstrap build --force --lax linux-xiaomi-merlin`.
Dau hieu nhan biet: build xong trong 2 phut = khong build; build that mat ~6 phut va thay
12-14 tien trinh `cc1`.

## Kiem chung symbol trong kernel — cach SAI

Tim chuoi `name_to_handle_at` trong anh kernel giai nen **luon tra 0** du co hay khong, vi
kallsyms luu ten symbol o dang nen theo token. Khong dung cach nay de xac nhan config.
Dung: so sanh sha256 cua kernel truoc/sau, hoac boot thu.
