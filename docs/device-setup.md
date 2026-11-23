# Первичная настройка устройства и проверки железа

Порядок, по которому устройство приводится в рабочее состояние с чистого носителя, и проверки,
которые дают паспорт [`docs/hardware.md`](hardware.md). Написано по итогам блока 1, с учётом того, что
на практике сработало, а что нет. Скрипты лежат в [`deploy/hwcheck/`](../deploy/hwcheck/).

Когда повторять: новый носитель (в том числе переход с microSD на USB SSD), замена экрана, кодека
или микрофона, переустановка ОС.

Обозначения: `<user>` — пользователь разработчика (сейчас `admin`). Команды без пометки выполняются на устройстве по SSH.

## 0. Что нужно

- Raspberry Pi Imager, носитель (целевой — USB SSD в синем порту USB 3.0), штатный блок 27 Вт.
- SSH-ключ на ПК (`ssh-keygen -t ed25519`), если нужен вход по ключу.
- На ПК — доступ к `dev-public.hailo.ai` и сайту Hailo Model Zoo. Из России без VPN он есть только у ПК,
  поэтому модели скачиваются на ПК и переносятся по `scp` (шаг 4).

## 1. Сборка (питание отключено)

- AI HAT+ 2 над Active Cooler, шлейф PCIe до упора, защёлки закрыты, зазор над кулером.
- CR2032 в держателе, кабель в J5. **Зарядку RTC не включать** (`dtparam=rtc_bbat_vchg` в `config.txt` не писать):
  CR2032 не перезаряжается.
- Экран — во **второй** micro-HDMI (так собрано сейчас: ALSA `vc4hdmi1`). Если подключить в первый, имена сменятся на `vc4hdmi0`
  и `HDMI-A-1`.
- Микрофон по §3.5: лицевая сторона, мягкая втулка, ветрозащита, подальше от динамиков и вентилятора.

## 2. ОС

1. Imager → Raspberry Pi 5 → Raspberry Pi OS (other) → **Raspberry Pi OS Lite (64-bit)**, Trixie.
   Не основной образ «Raspberry Pi OS (64-bit)»: в нём рабочий стол (`lightdm`), а §4 требует без него.
   Настройки образа: имя хоста `gamebox`, пользователь, Wi-Fi, страна, пояс `Europe/Moscow`, SSH.
   Сейчас включён вход и по паролю, и по ключу (решение владельца, домашняя сеть).
2. Первый запуск, затем с ПК: `ssh <user>@gamebox.local`.
3. Обновление и порядок загрузки:
   ```bash
   sudo apt update && sudo apt full-upgrade -y
   sudo rpi-eeprom-update -a && sudo reboot
   sudo rpi-eeprom-config --edit     # BOOT_ORDER=0xf14 ; PSU_MAX_CURRENT не добавлять
   sudo reboot
   ```
4. Если всё же стоит образ с рабочим столом — отключить его:
   ```bash
   sudo systemctl set-default multi-user.target
   sudo systemctl disable lightdm
   sudo reboot
   ```
5. Проверки:
   ```bash
   vcgencmd get_config usb_max_current_enable   # =1
   vcgencmd get_throttled                        # throttled=0x0
   findmnt -no SOURCE,FSTYPE,OPTIONS /           # ext4, noatime
   systemctl get-default                         # multi-user.target
   timedatectl                                   # пояс, synchronized: yes
   ```

## 3. Утилиты и скрипты

```bash
sudo apt install -y python3-numpy python3-evdev evtest edid-decode stress-ng jq curl \
     pciutils usbutils alsa-utils util-linux-extra strace
# на ПК, из корня репозитория:
scp -r deploy/hwcheck <user>@gamebox.local:~/hwcheck
# на устройстве:
mkdir -p ~/block1-report && cp ~/hwcheck/manual_notes.template.md ~/block1-report/manual_notes.md
cd ~/hwcheck
```

Все скрипты пишут результаты в `~/block1-report/`.

## 4. Hailo-10H

```bash
sudo apt install -y dkms hailo-h10-all     # не hailo-all: он для Hailo-8 и несовместим
sudo reboot
hailortcli fw-control identify             # Firmware Version 5.1.1, Device Architecture: HAILO10H
```

GenAI Model Zoo — той же версии, что HailoRT (`hailortcli --version`). Для 5.1.1 файл можно скачать на ПК
(`https://dev-public.hailo.ai/2025_12/Hailo10/hailo_gen_ai_model_zoo_5.1.1_arm64.deb`), перенести и поставить:

```bash
sudo dpkg -i hailo_gen_ai_model_zoo_5.1.1_arm64.deb
```

**Модель.** `/api/pull` без VPN не работает, а при неудачной загрузке `hailo-ollama` падает с `bad hash`.
Поэтому `.hef` для Hailo-10H скачивается на ПК с сайта Hailo Model Zoo, переносится и ставится скриптом:

```bash
scp Qwen2-1.5B-Instruct.hef <user>@gamebox.local:~        # на ПК
./hailo_install_hef.sh qwen2-instruct:1.5b ~/Qwen2-1.5B-Instruct.hef qwen2:1.5b
pkill hailo-ollama; MODEL=qwen2-instruct:1.5b ./60_hailo_smoke.sh
```

Скрипт проверяет архитектуру HEF, считает SHA-256, делает манифест на основе модели того же семейства и кладёт файл в
`/usr/share/hailo-ollama/models/blob/sha256_<хэш>`. Ошибку `pull` в начале smoke-скрипта можно игнорировать; признак
успеха — ответы `ru1`–`ru3`.

Не оставлять пустую папку `~/.config/hailo-ollama`: сервер падает на старте (`parse_error`).

## 5. Экран и сенсор

```bash
for c in /sys/class/drm/card*-HDMI-A-*; do echo "$c $(cat $c/status)"; head -3 $c/modes; done
sudo python3 20_touch_corners.py          # 4 угла + центр → touch.json, вывод «совпадает с картинкой»
aplay -L | grep -A1 '^hdmi'
speaker-test -D hdmi:CARD=vc4hdmi1,DEV=0 -c 2 -t wav -l 1
```

Громкость и яркость — кнопками экрана (рабочие значения 60 / 60). `plughw:` для HDMI на Pi 5 не работает.

## 6. Кодек и микрофон

```bash
arecord -l; cat /proc/asound/card*/usbid
amixer -c Device sset 'Auto Gain Control' off
alsamixer -c Device                        # F4 → Capture
sudo alsactl store
sudo python3 30_mic_check.py               # шум вентилятора, речь с 0,5 м, громко → mic/mic.json
```

Цели: клиппинга нет, речь выше шума ≥ 20 дБ, пик обычной речи −20…−3 dBFS. В блоке 1 запас был 1,5 дБ при
максимальном усилении (см. `hardware.md`). После смены микрофона или кодека повторить этот шаг первым.

## 7. HDMI после тишины

Тихая комната, рабочая громкость, ~4 минуты:

```bash
python3 40_hdmi_audio.py                   # → hdmi/hdmi.json
```

Смотреть `cold[].truncated_ms` (сколько начала съедено после 5/30/60 с тишины). Абсолютную задержку скрипт не меряет.

## 8. Раскладка §4.1 и своп

```bash
sudo ./10_setup_layout.sh                  # пользователь gamebox, каталоги, права; повторный запуск безопасен
swapon --show                              # только /dev/zram0
```

Если кроме zram подключён файл подкачки — drop-in `/etc/rpi/swap.conf.d/90-gamebox.conf` с `[Main]` / `Mechanism=zram`
(ключ сверить с `man swap.conf`), перезагрузка.

## 9. Питание и температура

Перед каждым прогоном — перезагрузка (сброс флагов `get_throttled`). Скрипт сам проверяет, что модель доступна.

```bash
sudo reboot
cd ~/hwcheck
sudo TAG=screen_from_pi DURATION_MIN=15 MODEL=qwen2-instruct:1.5b ./50_stress.sh
# без шума по HDMI:
sudo TAG=quiet WITH_AUDIO=0 DURATION_MIN=15 MODEL=qwen2-instruct:1.5b ./50_stress.sh
```

Итог — `stress_<TAG>/summary.json`. Нужно: `power_ok: true`, `ext5v_min_v` ≥ 4,8, `temp_max_c` < 80,
`hailo.failed` = 0 и `hailo.median_s` — секунды, а не миллисекунды (иначе Hailo фактически не работал).
Отдельное питание экрана — если `power_ok: false`, напряжение ниже 4,8 В или экран мерцает или гаснет.

## 10. Время загрузки и RTC

Три холодных старта (питание отключено ≥ 10 с, один раз ≥ 10 мин), секундомер до приглашения на экране, потом:

```bash
./70_boot_time.sh "холодный старт N"       # → boot_times.txt
dmesg | grep rpi-rtc                       # «setting system clock to …» должно быть текущее время, не 1970
```

## 11. Сбор и упаковка

```bash
sudo ./00_collect.sh                       # паспорт системы, только чтение
nano ~/block1-report/manual_notes.md
./90_pack.sh                               # ~/block1-report-<дата>.tar.gz
scp '<user>@gamebox.local:~/block1-report-*.tar.gz' .     # на ПК
```

Отчёт кладётся в `docs/hardware-report/<дата>/`, по нему обновляется `docs/hardware.md` и `versions.lock`.
