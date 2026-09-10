#!/usr/bin/env python3
"""
Victus Control - Telemetry & Thermal Profile Logger with Throttling Detection
Records thermal behavior, fan RPMs, clocks, and throttling events during workloads.
"""

import os
import sys
import time
import csv
import glob
import subprocess

LOG_FILE = "thermal_log.csv"

# ANSI Colors
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

class ThermalSensors:
    def __init__(self):
        self.cpu_temp_path = self._find_hwmon_sensor(["k10temp", "coretemp", "zenpower", "cpu"], ["tctl", "temp1_input", "input"])
        self.fan_paths = self._find_fan_paths()
        self.prev_cpu_times = None

    def _find_hwmon_sensor(self, name_hints, input_hints):
        for hwmon in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
            name_file = os.path.join(hwmon, "name")
            if not os.path.isfile(name_file):
                continue
            try:
                with open(name_file, "r") as f:
                    name = f.read().strip().lower()
            except Exception:
                continue
            if any(hint in name for hint in name_hints):
                for fpath in sorted(glob.glob(os.path.join(hwmon, "temp*_input"))):
                    return fpath
        return None

    def _find_fan_paths(self):
        for hwmon in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
            name_file = os.path.join(hwmon, "name")
            if not os.path.isfile(name_file):
                continue
            try:
                with open(name_file, "r") as f:
                    name = f.read().strip().lower()
            except Exception:
                continue
            if name == "hp":
                fan1 = os.path.join(hwmon, "fan1_input")
                fan2 = os.path.join(hwmon, "fan2_input")
                if os.path.isfile(fan1) and os.path.isfile(fan2):
                    return (fan1, fan2)
        return (None, None)

    def read_cpu_temp(self):
        if self.cpu_temp_path and os.path.isfile(self.cpu_temp_path):
            try:
                with open(self.cpu_temp_path, "r") as f:
                    val = float(f.read().strip())
                    return val / 1000.0 if val > 1000 else val
            except Exception:
                pass
        return 0.0

    def read_fans(self):
        f1_path, f2_path = self.fan_paths
        f1, f2 = 0, 0
        if f1_path and os.path.isfile(f1_path):
            try:
                with open(f1_path, "r") as f:
                    f1 = int(f.read().strip())
            except Exception:
                pass
        if f2_path and os.path.isfile(f2_path):
            try:
                with open(f2_path, "r") as f:
                    f2 = int(f.read().strip())
            except Exception:
                pass
        return f1, f2

    def read_cpu_usage(self):
        try:
            with open("/proc/stat", "r") as f:
                line = f.readline()
            parts = line.split()
            if parts[0] == "cpu":
                user = int(parts[1])
                nice = int(parts[2])
                system = int(parts[3])
                idle = int(parts[4])
                iowait = int(parts[5]) if len(parts) > 5 else 0
                irq = int(parts[6]) if len(parts) > 6 else 0
                softirq = int(parts[7]) if len(parts) > 7 else 0
                steal = int(parts[8]) if len(parts) > 8 else 0

                idle_all = idle + iowait
                total = user + nice + system + idle_all + irq + softirq + steal

                if self.prev_cpu_times:
                    prev_idle, prev_total = self.prev_cpu_times
                    diff_total = total - prev_total
                    diff_idle = idle_all - prev_idle
                    self.prev_cpu_times = (idle_all, total)
                    if diff_total > 0:
                        return max(0.0, min(100.0, (1.0 - diff_idle / diff_total) * 100.0))
                else:
                    self.prev_cpu_times = (idle_all, total)
                    return 0.0
        except Exception:
            pass
        return 0.0

    def read_cpu_freq_mhz(self):
        freqs = []
        for fpath in glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq"):
            try:
                with open(fpath, "r") as f:
                    freqs.append(float(f.read().strip()) / 1000.0)
            except Exception:
                pass
        return sum(freqs) / len(freqs) if freqs else 0.0

    def read_gpu(self):
        try:
            res = subprocess.run(
                ["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu", "--format=csv,noheader,nounits"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=1
            )
            if res.returncode == 0 and res.stdout.strip():
                parts = res.stdout.strip().split(",")
                if len(parts) >= 2:
                    return float(parts[0].strip()), float(parts[1].strip())
        except Exception:
            pass

        # Fallback to AMD iGPU
        for hwmon in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
            name_file = os.path.join(hwmon, "name")
            try:
                with open(name_file, "r") as f:
                    if "amdgpu" in f.read().lower():
                        temp_file = os.path.join(hwmon, "temp1_input")
                        if os.path.isfile(temp_file):
                            with open(temp_file, "r") as tf:
                                val = float(tf.read().strip()) / 1000.0
                                return val, 0.0
            except Exception:
                continue

        return 0.0, 0.0

    def read_gpu_throttled(self):
        try:
            res = subprocess.run(
                ["nvidia-smi", "--query-gpu=clocks_throttle_reasons.hw_thermal_slowdown,clocks_throttle_reasons.sw_thermal_slowdown", "--format=csv,noheader"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=1
            )
            if res.returncode == 0 and res.stdout.strip():
                out = res.stdout.strip().lower()
                return "active" in out
        except Exception:
            pass
        return False


def color_temp(temp):
    if temp >= 95:
        return f"{RED}{BOLD}{temp:4.1f}°C{RESET}"
    elif temp >= 85:
        return f"{RED}{temp:4.1f}°C{RESET}"
    elif temp >= 75:
        return f"{YELLOW}{temp:4.1f}°C{RESET}"
    elif temp >= 60:
        return f"{CYAN}{temp:4.1f}°C{RESET}"
    else:
        return f"{GREEN}{temp:4.1f}°C{RESET}"

def color_usage(pct):
    if pct >= 80:
        return f"{RED}{pct:5.1f}%{RESET}"
    elif pct >= 50:
        return f"{YELLOW}{pct:5.1f}%{RESET}"
    else:
        return f"{DIM}{pct:5.1f}%{RESET}"

def color_rpm(rpm):
    if rpm >= 5000:
        return f"{RED}{rpm:4d} RPM{RESET}"
    elif rpm >= 4000:
        return f"{YELLOW}{rpm:4d} RPM{RESET}"
    elif rpm >= 3000:
        return f"{CYAN}{rpm:4d} RPM{RESET}"
    else:
        return f"{GREEN}{rpm:4d} RPM{RESET}"


def main():
    sensors = ThermalSensors()
    records = []

    print(f"\n{BOLD}{CYAN}==================================================================================={RESET}")
    print(f"{BOLD}{CYAN}      Victus Control - Telemetri, Termal Profil ve Throttling Kaydedici           {RESET}")
    print(f"{BOLD}{CYAN}==================================================================================={RESET}")
    print(f"Log Dosyası: {BOLD}{LOG_FILE}{RESET}")
    print(f"CPU Modeli : {BOLD}AMD Ryzen 7 7840HS{RESET} (TjMax: 100°C, Boost Kısılma Eşiği: ~90°C)")
    print(f"GPU Modeli : {BOLD}NVIDIA GeForce RTX 4060 Laptop{RESET} (Termal Kısılma Eşiği: ~86.5°C)")
    print(f"Durdurmak için: {BOLD}{YELLOW}Ctrl + C{RESET} tuşlarına basın.\n")
    print(f"{DIM}Zaman  | CPU Sıcaklık / Yük / Saat   | GPU Sıcaklık / Yük | Fan1(CPU) | Fan2(GPU) | Durum{RESET}")
    print(f"{DIM}-------+-----------------------------+--------------------+-----------+-----------+---------{RESET}")

    start_time = time.time()
    sensors.read_cpu_usage()
    time.sleep(0.5)

    with open(LOG_FILE, "w", newline="") as csvfile:
        fieldnames = [
            "timestamp", "elapsed_s",
            "cpu_temp_c", "cpu_usage_pct", "cpu_freq_mhz",
            "gpu_temp_c", "gpu_usage_pct", "gpu_throttled",
            "fan1_rpm", "fan2_rpm", "thermal_status"
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        try:
            while True:
                now = time.time()
                elapsed = now - start_time
                timestamp_str = time.strftime("%H:%M:%S")

                cpu_temp = sensors.read_cpu_temp()
                cpu_usage = sensors.read_cpu_usage()
                cpu_freq = sensors.read_cpu_freq_mhz()
                gpu_temp, gpu_usage = sensors.read_gpu()
                gpu_throttled = sensors.read_gpu_throttled()
                fan1_rpm, fan2_rpm = sensors.read_fans()

                # Determine throttling status
                if cpu_temp >= 95.0 or gpu_throttled:
                    status_text = "THROTTLING"
                    status_disp = f"{RED}{BOLD}THROTTLE!{RESET}"
                elif cpu_temp >= 90.0 or gpu_temp >= 83.0:
                    status_text = "WARN_HOT"
                    status_disp = f"{YELLOW}{BOLD}ÇOK SICAK{RESET}"
                elif cpu_temp >= 80.0:
                    status_text = "HEAVY_LOAD"
                    status_disp = f"{CYAN}AĞIR YÜK{RESET}"
                else:
                    status_text = "NORMAL"
                    status_disp = f"{GREEN}NORMAL{RESET}"

                row = {
                    "timestamp": timestamp_str,
                    "elapsed_s": round(elapsed, 1),
                    "cpu_temp_c": round(cpu_temp, 1),
                    "cpu_usage_pct": round(cpu_usage, 1),
                    "cpu_freq_mhz": round(cpu_freq, 0),
                    "gpu_temp_c": round(gpu_temp, 1),
                    "gpu_usage_pct": round(gpu_usage, 1),
                    "gpu_throttled": int(gpu_throttled),
                    "fan1_rpm": fan1_rpm,
                    "fan2_rpm": fan2_rpm,
                    "thermal_status": status_text
                }
                writer.writerow(row)
                csvfile.flush()
                records.append(row)

                time_disp = f"{int(elapsed//60):02d}:{int(elapsed%60):02d}"
                cpu_disp = f"{color_temp(cpu_temp)} {color_usage(cpu_usage)} {cpu_freq:4.0f}MHz"
                gpu_disp = f"{color_temp(gpu_temp)} {color_usage(gpu_usage)}"
                f1_disp = color_rpm(fan1_rpm)
                f2_disp = color_rpm(fan2_rpm)

                sys.stdout.write(f"\r{time_disp}  | {cpu_disp} | {gpu_disp}   | {f1_disp} | {f2_disp} | {status_disp}\n")
                sys.stdout.flush()

                time.sleep(1.0)

        except KeyboardInterrupt:
            print(f"\n\n{BOLD}{GREEN}✓ Kayıt Durduruldu! ({len(records)} saniyelik veri toplandı){RESET}\n")

    # Final Analysis
    if records:
        cpu_temps = [r["cpu_temp_c"] for r in records if r["cpu_temp_c"] > 0]
        gpu_temps = [r["gpu_temp_c"] for r in records if r["gpu_temp_c"] > 0]
        cpu_usages = [r["cpu_usage_pct"] for r in records]
        f1_rpms = [r["fan1_rpm"] for r in records]
        f2_rpms = [r["fan2_rpm"] for r in records]
        throttle_seconds = sum(1 for r in records if r["thermal_status"] == "THROTTLING")
        warn_seconds = sum(1 for r in records if r["thermal_status"] == "WARN_HOT")

        print(f"{BOLD}=== TEST SEANSI VE THROTTLING ÖZETİ ==={RESET}")
        print(f"Toplam Süre       : {int(elapsed//60)} dk {int(elapsed%60)} sn")
        if cpu_temps:
            print(f"CPU Sıcaklık      : Min: {min(cpu_temps):.1f}°C  |  Ort: {sum(cpu_temps)/len(cpu_temps):.1f}°C  |  {BOLD}{RED}Maks: {max(cpu_temps):.1f}°C{RESET}")
        if gpu_temps:
            print(f"GPU Sıcaklık      : Min: {min(gpu_temps):.1f}°C  |  Ort: {sum(gpu_temps)/len(gpu_temps):.1f}°C  |  {BOLD}{RED}Maks: {max(gpu_temps):.1f}°C{RESET}")
        if cpu_usages:
            print(f"CPU Kullanımı     : Ort: {sum(cpu_usages)/len(cpu_usages):.1f}%  |  Maks: {max(cpu_usages):.1f}%")
        if f1_rpms:
            print(f"Fan 1 (CPU)       : Min: {min(f1_rpms)} RPM  |  Maks: {max(f1_rpms)} RPM")
        if f2_rpms:
            print(f"Fan 2 (GPU)       : Min: {min(f2_rpms)} RPM  |  Maks: {max(f2_rpms)} RPM")

        print(f"\n{BOLD}--- Termal Kısılma (Throttling) Analizi ---{RESET}")
        if throttle_seconds > 0:
            print(f"{RED}{BOLD}⚠ KRİTİK KISILMA: Sistem {throttle_seconds} saniye boyunca aktif termal kısmaya girdi!{RESET}")
        elif warn_seconds > 0:
            print(f"{YELLOW}⚠ YÜKSEK ISI UYARISI: Sistem {warn_seconds} saniye boyunca 90°C üzerinde çalıştı (Boost saatleri hafif kırpılmış olabilir).{RESET}")
        else:
            print(f"{GREEN}✓ KUSURSUZ: Sistem hiçbir zaman termal kısmaya (throttling) girmedi.{RESET}")

        print(f"\n{BOLD}{GREEN}Log dosyası hazır: {LOG_FILE}{RESET}")

if __name__ == "__main__":
    main()
