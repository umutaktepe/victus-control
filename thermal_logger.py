#!/usr/bin/env python3
"""
Victus Control - Telemetry & Thermal Profile Logger
Records thermal behavior, fan RPMs, and hardware usage during real-world workloads.
"""

import os
import sys
import time
import csv
import glob
import subprocess
import signal

LOG_FILE = "thermal_log.csv"

# ANSI Colors
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
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
                # Search for input files
                for fpath in sorted(glob.glob(os.path.join(hwmon, "temp*_input"))):
                    return fpath
        return None

    def _find_fan_paths(self):
        # Look for hp hwmon with fan1_input and fan2_input
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

    def read_gpu(self):
        # Queries nvidia-smi
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

        # Fallback to AMD iGPU hwmon if dGPU is sleeping
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


def color_temp(temp):
    if temp >= 85:
        return f"{RED}{BOLD}{temp:4.1f}°C{RESET}"
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

def color_rpm(rpm, max_rpm=6000):
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

    print(f"\n{BOLD}{CYAN}=================================================================={RESET}")
    print(f"{BOLD}{CYAN}   Victus Control - Telemetri ve Termal Profil Kaydedici         {RESET}")
    print(f"{BOLD}{CYAN}=================================================================={RESET}")
    print(f"Log Dosyası: {BOLD}{LOG_FILE}{RESET}")
    print(f"Durdurmak için: {BOLD}{YELLOW}Ctrl + C{RESET} tuşlarına basın.\n")
    print(f"{DIM}Zaman    | CPU Sıcaklık  Yük  | GPU Sıcaklık  Yük  | Fan 1 (CPU) | Fan 2 (GPU){RESET}")
    print(f"{DIM}---------+--------------------+--------------------+-------------+------------{RESET}")

    start_time = time.time()

    # Pre-sample CPU usage baseline
    sensors.read_cpu_usage()
    time.sleep(0.5)

    with open(LOG_FILE, "w", newline="") as csvfile:
        fieldnames = [
            "timestamp", "elapsed_s",
            "cpu_temp_c", "cpu_usage_pct",
            "gpu_temp_c", "gpu_usage_pct",
            "fan1_rpm", "fan2_rpm"
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
                gpu_temp, gpu_usage = sensors.read_gpu()
                fan1_rpm, fan2_rpm = sensors.read_fans()

                row = {
                    "timestamp": timestamp_str,
                    "elapsed_s": round(elapsed, 1),
                    "cpu_temp_c": round(cpu_temp, 1),
                    "cpu_usage_pct": round(cpu_usage, 1),
                    "gpu_temp_c": round(gpu_temp, 1),
                    "gpu_usage_pct": round(gpu_usage, 1),
                    "fan1_rpm": fan1_rpm,
                    "fan2_rpm": fan2_rpm
                }
                writer.writerow(row)
                csvfile.flush()
                records.append(row)

                # Format terminal display
                time_disp = f"{int(elapsed//60):02d}:{int(elapsed%60):02d}"
                cpu_disp = f"{color_temp(cpu_temp)}  {color_usage(cpu_usage)}"
                gpu_disp = f"{color_temp(gpu_temp)}  {color_usage(gpu_usage)}"
                f1_disp = color_rpm(fan1_rpm)
                f2_disp = color_rpm(fan2_rpm)

                sys.stdout.write(f"\r{time_disp}    | {cpu_disp} | {gpu_disp} | {f1_disp}  | {f2_disp}\n")
                sys.stdout.flush()

                time.sleep(1.0)

        except KeyboardInterrupt:
            print(f"\n\n{BOLD}{GREEN}✓ Kayıt Durduruldu! ({len(records)} saniyelik veri toplandı){RESET}\n")

    # Generate Summary
    if records:
        cpu_temps = [r["cpu_temp_c"] for r in records if r["cpu_temp_c"] > 0]
        gpu_temps = [r["gpu_temp_c"] for r in records if r["gpu_temp_c"] > 0]
        cpu_usages = [r["cpu_usage_pct"] for r in records]
        f1_rpms = [r["fan1_rpm"] for r in records]
        f2_rpms = [r["fan2_rpm"] for r in records]

        print(f"{BOLD}=== TEST SEANSI ÖZETİ ==={RESET}")
        print(f"Toplam Süre   : {int(elapsed//60)} dk {int(elapsed%60)} sn")
        if cpu_temps:
            print(f"CPU Sıcaklık  : Min: {min(cpu_temps):.1f}°C  |  Ort: {sum(cpu_temps)/len(cpu_temps):.1f}°C  |  {BOLD}{RED}Maks: {max(cpu_temps):.1f}°C{RESET}")
        if gpu_temps:
            print(f"GPU Sıcaklık  : Min: {min(gpu_temps):.1f}°C  |  Ort: {sum(gpu_temps)/len(gpu_temps):.1f}°C  |  {BOLD}{RED}Maks: {max(gpu_temps):.1f}°C{RESET}")
        if cpu_usages:
            print(f"CPU Kullanımı : Ort: {sum(cpu_usages)/len(cpu_usages):.1f}%  |  Maks: {max(cpu_usages):.1f}%")
        if f1_rpms:
            print(f"Fan 1 (CPU)   : Min: {min(f1_rpms)} RPM  |  Maks: {max(f1_rpms)} RPM")
        if f2_rpms:
            print(f"Fan 2 (GPU)   : Min: {min(f2_rpms)} RPM  |  Maks: {max(f2_rpms)} RPM")
        print(f"\n{BOLD}{GREEN}Log kaydedildi: {LOG_FILE}{RESET}")
        print(f"Bu verilerle Antigravity size en ideal fan eğrisini çıkaracaktır.")

if __name__ == "__main__":
    main()
