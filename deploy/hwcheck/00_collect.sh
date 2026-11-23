#!/usr/bin/env bash
# Game Box, блок 1. Сбор паспорта железа и системы. Только чтение, ничего не меняет.
# Запуск:  sudo ./00_collect.sh
# Результат: ~/block1-report/collect/*.txt
set -u
U="${SUDO_USER:-$USER}"
H="$(getent passwd "$U" | cut -d: -f6)"
OUT="${OUT:-$H/block1-report}"
D="$OUT/collect"
mkdir -p "$D"

run() { # run <имя файла> <команда в виде строки>
  local name="$1"; shift
  { echo "\$ $1"; bash -c "$1" 2>&1; echo "[exit=$?]"; echo; } >> "$D/$name.txt"
}
: > /dev/null
rm -f "$D"/*.txt
echo "Собираю в $D ..."

# --- ОС и плата
run os 'cat /etc/os-release'
run os 'cat /etc/rpi-issue'
run os 'uname -a'
run os 'python3 --version'
run os 'cat /proc/device-tree/model; echo'
run os 'grep -E "Revision|Model" /proc/cpuinfo'
run os 'free -h'
run os 'vcgencmd version'

# --- EEPROM и загрузка
run eeprom 'rpi-eeprom-update'
run eeprom 'rpi-eeprom-config'
run eeprom 'vcgencmd bootloader_version'
run boot 'cat /boot/firmware/config.txt'
run boot 'cat /boot/firmware/cmdline.txt'

# --- Питание
run power 'vcgencmd get_config usb_max_current_enable'
run power 'for f in /proc/device-tree/chosen/power/*; do printf "%s: " "$f"; od -An -tu4 --endian=big "$f" | tr -s " "; done'
run power 'vcgencmd get_throttled'
run power 'vcgencmd pmic_read_adc'
run power 'dmesg | grep -iE "under-?voltage|over-?current|power supply|pd |usb_max|psu" || true'

# --- Температура и вентилятор
run thermal 'vcgencmd measure_temp'
run thermal 'vcgencmd measure_clock arm'
run thermal 'cat /sys/devices/platform/cooling_fan/hwmon/*/fan1_input'
run thermal 'for c in /sys/class/thermal/cooling_device*; do echo "$c $(cat $c/type) $(cat $c/cur_state)/$(cat $c/max_state)"; done'

# --- Диск
run storage 'lsblk -o NAME,MODEL,SIZE,TRAN,FSTYPE,MOUNTPOINT,PARTUUID'
run storage 'findmnt -no SOURCE,FSTYPE,OPTIONS /'
run storage 'cat /etc/fstab'
run storage 'df -h'
run storage 'tune2fs -l "$(findmnt -no SOURCE /)" | grep -iE "features|mount options|state|block size|Reserved block count"'
run storage 'lsusb -t'
run swap 'swapon --show'
run swap 'zramctl'
run swap 'cat /etc/rpi/swap.conf; ls -la /etc/rpi/swap.conf.d/ 2>/dev/null; cat /etc/rpi/swap.conf.d/*.conf 2>/dev/null'
run swap 'cat /proc/sys/vm/swappiness'

# --- USB, PCIe
run usb 'lsusb'
run usb 'lsusb -t'
run usb 'for c in /proc/asound/card*; do [ -f $c/usbid ] && echo "$c id=$(cat $c/id) usbid=$(cat $c/usbid)"; done'
run usb_verbose 'lsusb -v'
run pci 'lspci -nn'
run pci 'lspci -vv | grep -iE "^[0-9a-f]|LnkCap:|LnkSta:"'

# --- Hailo
run hailo 'hailortcli --version'
run hailo 'hailortcli fw-control identify'
run hailo 'dpkg -l | grep -iE "hailo|hailort"'
run hailo 'ls -l /dev/hailo* '
run hailo 'lsmod | grep -i hailo'
run hailo 'for m in $(lsmod | awk "/hailo/{print \$1}"); do modinfo $m | grep -E "^(filename|version|vermagic|name):"; done'
run hailo 'dmesg | grep -i hailo'
run hailo 'curl -s --max-time 5 http://localhost:8000/hailo/v1/list || echo "hailo-ollama не запущен"'
run hailo 'find /usr /opt /home /root /var -xdev -type f \( -name "*.hef" -o -name "*.gguf" \) -size +5M -printf "%s\t%p\n" 2>/dev/null'

# --- Экран
run display 'for c in /sys/class/drm/card*-*; do echo "== $c status=$(cat $c/status 2>/dev/null) enabled=$(cat $c/enabled 2>/dev/null)"; cat $c/modes 2>/dev/null; done'
run display 'for c in /sys/class/drm/card*-HDMI-A-*; do [ "$(cat $c/status)" = connected ] && edid-decode "$c/edid"; done'
run display 'cat /sys/class/graphics/fb0/virtual_size 2>/dev/null; echo'
run display 'kmsprint 2>/dev/null || echo "kmsprint нет"'
run input 'cat /proc/bus/input/devices'
run input 'ls -l /dev/input/by-id/ /dev/input/by-path/'

# --- Звук
run audio 'aplay -l'
run audio 'aplay -L'
run audio 'arecord -l'
run audio 'arecord -L'
run audio 'cat /proc/asound/cards'
run audio 'for n in $(awk "/^ *[0-9]+ \[/{print \$1}" /proc/asound/cards); do echo "=== card $n"; amixer -c $n contents; done'
run audio 'for c in /proc/asound/card*; do for s in $c/stream*; do [ -f $s ] && { echo "== $s"; cat $s; }; done; done'

# --- Сеть, SSH, mDNS
run net 'hostnamectl'
run net 'ip -br addr'
run net 'iw dev 2>/dev/null; iw dev wlan0 link 2>/dev/null'
run net 'systemctl is-active avahi-daemon ssh'
run net 'avahi-resolve -n gamebox.local 2>&1 || true'
run net 'sshd -T 2>/dev/null | grep -iE "^(passwordauthentication|pubkeyauthentication|permitrootlogin|kbdinteractiveauthentication) "'

# --- Время и RTC
run time 'timedatectl'
run time 'timedatectl show-timesync --all 2>/dev/null | head -20'
run time 'command -v hwclock >/dev/null && hwclock -r || echo "hwclock нет (пакет util-linux-extra); RTC см. строку rpi-rtc в dmesg"'
run time 'for f in $(find /sys/devices/platform -path "*rtc*" \( -name battery_voltage -o -name charging_voltage \) 2>/dev/null); do echo "$f: $(cat $f)"; done'
run time 'grep -n rtc_bbat /boot/firmware/config.txt || echo "rtc_bbat_vchg не задан (зарядка выключена) — правильно для CR2032"'
run time 'dmesg | grep -iE "rtc" '

# --- Загрузка
run boottime 'systemctl get-default; systemctl is-enabled lightdm 2>&1; systemctl is-active lightdm 2>&1'
run boottime 'systemd-analyze'
run boottime 'systemd-analyze blame | head -30'
run boottime 'systemd-analyze critical-chain'
run boottime 'systemctl --failed'

# --- Раскладка §4.1
run layout 'id gamebox'
run layout 'ls -ld /opt/gamebox /var/lib/gamebox /var/lib/gamebox/* /etc/gamebox'
run layout 'id '"$U"

# --- Пакеты (для versions.lock)
dpkg-query -W -f='${Package}\t${Version}\t${Architecture}\n' > "$D/packages.tsv" 2>/dev/null
run services 'systemctl list-units --type=service --state=running --no-pager'
run journal 'journalctl -b -p warning --no-pager | tail -200'

echo "Готово: $(ls "$D" | wc -l) файлов в $D"
chown -R "$U":"$U" "$OUT" 2>/dev/null || true
