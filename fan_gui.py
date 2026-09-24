#!/usr/bin/env python3
import sys
import os
import glob
import subprocess
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QSlider, QGroupBox
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont

class VictusFanControl(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

        hwmon_paths = glob.glob('/sys/devices/platform/hp-wmi/hwmon/hwmon*')
        self.hwmon_path = hwmon_paths[0] if hwmon_paths else None

        # Anlık verileri güncelleme döngüsü (1 saniye)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_live_data)
        self.timer.start(1000)

        self.update_live_data()

    def initUI(self):
        self.setWindowTitle('Omen 16 Control Center')
        self.setMinimumSize(400, 400)
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)

        main_layout = QVBoxLayout()

        # --- 1. LIVE STATUS PANEL ---
        self.status_label = QLabel('📊 Fetching live status...')
        self.status_label.setFont(QFont('Sans Serif', 10, QFont.Weight.Bold))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("background-color: #2a2a2a; color: #ffffff; padding: 10px; border-radius: 6px;")
        main_layout.addWidget(self.status_label)
        main_layout.addSpacing(10)

        # --- 2. GLOBAL MODES SECTION ---
        self.btn_max = QPushButton('⚡ MAX Mode (Full Speed)')
        self.btn_better = QPushButton('🧠 BETTER AUTO (Smart Software)')
        self.btn_auto = QPushButton('🤖 AUTO Mode (Factory BIOS)')

        self.mode_buttons = [self.btn_max, self.btn_better, self.btn_auto]
        self.btn_max.clicked.connect(lambda: self.run_action(1))
        self.btn_better.clicked.connect(lambda: self.run_action(2))
        self.btn_auto.clicked.connect(lambda: self.run_action(3))

        for btn in self.mode_buttons:
            btn.setFont(QFont('Sans Serif', 9))
            btn.setMinimumHeight(35)
            # HACK: Pencere ilk açıldığında butonun otomatik olarak turuncu odak rengini kapmasını engeller
            btn.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            main_layout.addWidget(btn)

        main_layout.addSpacing(15)

        # --- 3. DYNAMIC MANUAL CONTROL (SLIDERS) ---
        # CPU Slider Group
        cpu_group = QGroupBox("🛠️ Custom CPU Fan Speed")
        cpu_group.setFont(QFont('Sans Serif', 9, QFont.Weight.Bold))
        cpu_box = QVBoxLayout()

        self.cpu_val_label = QLabel('Target: 4000 RPM')
        self.cpu_val_label.setFont(QFont('Sans Serif', 9))

        self.cpu_slider = QSlider(Qt.Orientation.Horizontal)
        self.cpu_slider.setRange(20, 58)
        self.cpu_slider.setSingleStep(1)
        self.cpu_slider.setValue(40)
        self.cpu_slider.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.cpu_slider.valueChanged.connect(self.on_cpu_slider_move)
        self.cpu_slider.sliderReleased.connect(self.apply_cpu_speed)

        cpu_box.addWidget(self.cpu_val_label)
        cpu_box.addWidget(self.cpu_slider)
        cpu_group.setLayout(cpu_box)
        main_layout.addWidget(cpu_group)

        # GPU Slider Group
        gpu_group = QGroupBox("🛠️ Custom GPU Fan Speed")
        gpu_group.setFont(QFont('Sans Serif', 9, QFont.Weight.Bold))
        gpu_box = QVBoxLayout()

        self.gpu_val_label = QLabel('Target: 4500 RPM')
        self.gpu_val_label.setFont(QFont('Sans Serif', 9))

        self.gpu_slider = QSlider(Qt.Orientation.Horizontal)
        self.gpu_slider.setRange(20, 61)
        self.gpu_slider.setSingleStep(1)
        self.gpu_slider.setValue(45)
        self.gpu_slider.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.gpu_slider.valueChanged.connect(self.on_gpu_slider_move)
        self.gpu_slider.sliderReleased.connect(self.apply_gpu_speed)

        gpu_box.addWidget(self.gpu_val_label)
        gpu_box.addWidget(self.gpu_slider)
        gpu_group.setLayout(gpu_box)
        main_layout.addWidget(gpu_group)

        self.setLayout(main_layout)

    def on_cpu_slider_move(self, val):
        self.cpu_val_label.setText(f'Target: {val * 100} RPM')

    def on_gpu_slider_move(self, val):
        self.gpu_val_label.setText(f'Target: {val * 100} RPM')

    def apply_cpu_speed(self):
        speed = self.cpu_slider.value() * 100
        subprocess.run(["pkexec", "/home/umutaktepe/victus-control/fan_selector.sh", "--execute-root", "4", str(speed)])

    def apply_gpu_speed(self):
        speed = self.gpu_slider.value() * 100
        subprocess.run(["pkexec", "/home/umutaktepe/victus-control/fan_selector.sh", "--execute-root", "5", str(speed)])

    def run_action(self, action_id):
        subprocess.run(["pkexec", "/home/umutaktepe/victus-control/fan_selector.sh", "--execute-root", str(action_id)])
        self.update_live_data()

    def update_live_data(self):
        if not self.hwmon_path:
            self.status_label.setText("❌ Error: Hwmon directory not found.")
            return

        try:
            with open(f"{self.hwmon_path}/fan1_input", "r") as f:
                cpu_rpm = f.read().strip()
            with open(f"{self.hwmon_path}/fan2_input", "r") as f:
                gpu_rpm = f.read().strip()

            self.status_label.setText(f"📊 LIVE:  CPU: {cpu_rpm} RPM  |  GPU: {gpu_rpm} RPM")

            with open(f"{self.hwmon_path}/pwm1_enable", "r") as f:
                mode_val = f.read().strip()

            service_active = subprocess.run(['systemctl', 'is-active', '--quiet', 'victus-backend.service']).returncode == 0

            # Önce tüm buton stillerini sıfırla (KDE orijinal temasına döner)
            for btn in self.mode_buttons:
                btn.setStyleSheet("")

            # Aktif mod için göz alıcı Premium Turuncu stil şablonu
            active_style = "background-color: #e65c00; color: white; font-weight: bold; border: 1px solid #ff7711; border-radius: 4px;"

            # Donanımdaki mutlak gerçeğe göre sadece ilgili butonu turuncu yap
            if mode_val == "0":
                self.btn_max.setStyleSheet(active_style)
            elif mode_val == "2":
                self.btn_auto.setStyleSheet(active_style)
            elif mode_val == "1":
                if service_active:
                    self.btn_better.setStyleSheet(active_style)
        except Exception as e:
            pass

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = VictusFanControl()
    ex.show()
    sys.exit(app.exec())
