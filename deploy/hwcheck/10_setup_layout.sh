#!/usr/bin/env bash
# Game Box, блок 1. Системный пользователь и раскладка диска §4.1. Идемпотентно.
# Запуск:  sudo ./10_setup_layout.sh
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Запусти через sudo"; exit 1; }
DEV_USER="${SUDO_USER:-}"

# 1. Системный пользователь gamebox: без входа, дом — /var/lib/gamebox
if ! id gamebox &>/dev/null; then
  useradd --system --user-group --home-dir /var/lib/gamebox --no-create-home \
          --shell /usr/sbin/nologin gamebox
  echo "Создан пользователь gamebox"
fi
for g in audio video render input; do
  getent group "$g" >/dev/null && usermod -aG "$g" gamebox
done
# доступ к Hailo: если /dev/hailo0 принадлежит отдельной группе — добавим и её
if [ -e /dev/hailo0 ]; then
  hg="$(stat -c %G /dev/hailo0)"
  [ "$hg" != root ] && usermod -aG "$hg" gamebox
fi

# 2. Каталоги
install -d -o root    -g root    -m 0755 /opt/gamebox
install -d -o gamebox -g gamebox -m 0750 /var/lib/gamebox
for d in games packs personas models resources db tts_cache logs audio_debug; do
  install -d -o gamebox -g gamebox -m 0750 "/var/lib/gamebox/$d"
done
install -d -o root -g gamebox -m 0750 /etc/gamebox

# 3. Разработчик в группе gamebox: может читать журналы и базы без sudo
if [ -n "$DEV_USER" ] && [ "$DEV_USER" != root ]; then
  usermod -aG gamebox "$DEV_USER"
  echo "Пользователь $DEV_USER добавлен в группу gamebox (перелогинься)"
fi

# 4. Проверки, которые скрипт только сообщает (правки — вручную по инструкции)
src="$(findmnt -no SOURCE /)"
opts="$(findmnt -no OPTIONS /)"
fs="$(findmnt -no FSTYPE /)"
echo "Корень: $src ($fs), опции: $opts"
[ "$fs" = ext4 ] || echo "ВНИМАНИЕ: корень не ext4"
tune2fs -l "$src" | grep -q has_journal && echo "ext4: журнал есть" || echo "ВНИМАНИЕ: журнала ext4 нет"
echo "$opts" | grep -q noatime && echo "noatime: есть" || echo "ВНИМАНИЕ: noatime нет — добавь в /etc/fstab (шаг 8 инструкции)"
echo "Своп:"; swapon --show || true

echo
ls -ld /opt/gamebox /var/lib/gamebox /var/lib/gamebox/* /etc/gamebox
id gamebox
