#!/bin/bash

# --- ROOT PRIVILEGED EXECUTION ZONE ---
if [ "${1:-}" = "--execute-root" ]; then
    ACTION=$2
    CUSTOM_SPEED=$3

    case "$ACTION" in
        1) # ⚡ MAX Mode
            # Arka plandaki Better Auto döngüsü bizimle savaşmasın diye servisi durduruyoruz
            systemctl stop victus-backend.service
            bash /home/umutaktepe/victus-control/backend/src/set-fan-mode.sh MANUAL
            bash /home/umutaktepe/victus-control/backend/src/set-fan-mode.sh MAX
            ;;
        2) # 🧠 BETTER AUTO Mode
            # Akıllı yazılım modunu istediğimizde servisi tekrar ateşliyoruz, o zaten döngüyü başlatıyor
            bash /home/umutaktepe/victus-control/backend/src/set-fan-mode.sh BETTER_AUTO
            systemctl start victus-backend.service
            ;;
        3) # 🤖 AUTO Mode (Factory BIOS)
            systemctl stop victus-backend.service
            bash /home/umutaktepe/victus-control/backend/src/set-fan-mode.sh MANUAL
            bash /home/umutaktepe/victus-control/backend/src/set-fan-mode.sh AUTO
            ;;
        4) # 🛠️ Lock CPU Fan (Dynamic Slider)
            systemctl stop victus-backend.service
            SPEED=${CUSTOM_SPEED:-4000}
            bash /home/umutaktepe/victus-control/backend/src/set-fan-mode.sh MANUAL
            bash /home/umutaktepe/victus-control/backend/src/set-fan-speed.sh 1 "$SPEED"
            ;;
        5) # 🛠️ Lock GPU Fan (Dynamic Slider)
            systemctl stop victus-backend.service
            SPEED=${CUSTOM_SPEED:-4500}
            bash /home/umutaktepe/victus-control/backend/src/set-fan-mode.sh MANUAL
            bash /home/umutaktepe/victus-control/backend/src/set-fan-speed.sh 2 "$SPEED"
            ;;
    esac
    exit 0
fi

# --- USER SPACE ZONE (Fallback Menu) ---
L_MAX="⚡ MAX Mode (Full Speed)"
L_BETTER="🧠 BETTER AUTO (Smart Software)"
L_AUTO="🤖 AUTO Mode (Factory BIOS)"
MENU_HEADER="Please select a fan mode:"

HWMON_PATH=$(find /sys/devices/platform/hp-wmi/hwmon -mindepth 1 -maxdepth 1 -type d -name "hwmon*" | head -n 1 2>/dev/null)
if [ -n "$HWMON_PATH" ]; then
    CPU_RPM=$(cat "$HWMON_PATH/fan1_input" 2>/dev/null | tr -d '[:space:]')
    GPU_RPM=$(cat "$HWMON_PATH/fan2_input" 2>/dev/null | tr -d '[:space:]')
    MENU_HEADER="📊 LIVE STATUS:  CPU: ${CPU_RPM:-0} RPM  |  GPU: ${GPU_RPM:-0} RPM\n\nSelect a fan mode:"

    MODE_VAL=$(cat "$HWMON_PATH/pwm1_enable" 2>/dev/null | tr -d '[:space:]')
    case "$MODE_VAL" in
        0) L_MAX="$L_MAX  ➔ ACTIVE" ;;
        2) L_AUTO="$L_AUTO  ➔ ACTIVE" ;;
        1) L_BETTER="$L_BETTER  ➔ ACTIVE" ;;
    esac
fi

CHOSEN_MODE=$(kdialog --title "Victus 16 Fan Management" --geometry 440x260 --menu "$MENU_HEADER" \
  "1" "$L_MAX" \
  "2" "$L_BETTER" \
  "3" "$L_AUTO")

[ -z "$CHOSEN_MODE" ] && exit 0
pkexec /home/umutaktepe/victus-control/fan_selector.sh --execute-root "$CHOSEN_MODE"
