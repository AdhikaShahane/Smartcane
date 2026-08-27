# SMARTCANE — Speech-Controlled, Vision-Enabled Assistive Robotic Brain

SmartCane is an autonomous AI robotic brain designed to assist visually impaired individuals. It runs as a background service on a **Raspberry Pi** and operates using real-time sensor processing, computer vision, and speech recognition.

---

## 1. Core Architecture & Philosophy

The system treats the cane as a complete robotic entity:
- **Eyes:** Camera sensor (USB 2.0 HD UVC Webcam or Raspberry Pi Camera Module 3).
- **Ears:** Microphone with noise cancellation and hands-free voice intake.
- **Voice:** Grounded natural text-to-speech engine.
- **Sensors:** MPU6050 6-DOF IMU, HC-SR04 Ultrasonic proximity sensor, GPS.
- **Brain:** Central AI Orchestrator running local sensor fusion and Gemini intelligence.

---

## 2. Step-Length Estimation Mathematics

SmartCane uses the real-time dynamic gait stride formula:

$$\text{SL} = K \times \sqrt[4]{a_{\max} - a_{\min}}$$

Where:
- $\text{SL}$ = Estimated step/stride length in meters (typically 0.40m – 0.95m).
- $K$ = User-calibrated constant (default $\approx 0.45$, adjustable via calibration).
- $a_{\max}$ = Maximum acceleration measured during the walking-step interval ($\text{m/s}^2$).
- $a_{\min}$ = Minimum acceleration measured during the walking-step interval ($\text{m/s}^2$).

### Distance-to-Steps Conversion

$$\text{Steps} = \text{round}\left(\frac{\text{Distance}}{\text{SL}}\right)$$

Spoken guidance expresses distance directly in actionable steps:
> *"The chair is ahead. Take approximately 3 steps forward."*

---

## 3. Hardware Pinout & Wiring (Raspberry Pi 4 / 5)

| Sensor | Sensor Pin | Raspberry Pi Pin | Pin Description |
| :--- | :--- | :--- | :--- |
| **MPU6050** | VCC | Pin 1 | 3.3V Power |
| **MPU6050** | GND | Pin 6 | Ground |
| **MPU6050** | SDA | Pin 3 (GPIO 2) | I2C Data |
| **MPU6050** | SCL | Pin 5 (GPIO 3) | I2C Clock |
| **HC-SR04** | VCC | Pin 2 | 5V Power |
| **HC-SR04** | GND | Pin 9 | Ground |
| **HC-SR04** | TRIG | Pin 16 (GPIO 23) | Trigger Pulse |
| **HC-SR04** | ECHO | Pin 18 (GPIO 24) | Echo Pulse (use 1k/2k divider) |
| **Camera** | Ribbon / USB | CSI Port / USB | V4L2 / Picamera2 |
| **Audio** | USB / 3.5mm | USB / Audio Jack | ALSA Mic / Speaker |

---

## 4. Headless Autonomous Service Deployment (Raspberry Pi)

All standalone Raspberry Pi deployment files are located in `/smartcane_pi/`:

1. **Install Dependencies:**
   ```bash
   sudo apt update && sudo apt install -y python3-pip python3-smbus i2c-tools python3-rpi.gpio espeak ffmpeg libportaudio2
   cd /home/pi/smartcane
   pip3 install -r requirements.txt --break-system-packages
   ```

2. **Calibrate K Factor:**
   ```bash
   python3 calibrate_k.py
   ```

3. **Install Systemd Auto-Start Service:**
   ```bash
   sudo cp smartcane_pi/smartcane.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable smartcane.service
   sudo systemctl start smartcane.service
   ```

---

## 5. Spoken Response Protocols

| Priority | Trigger | Spoken Format | Example |
| :--- | :--- | :--- | :--- |
| **Tier 1 (Immediate)** | Obstacle $< 0.6\text{m}$ / Ultrasonic $< 60\text{cm}$ | Immediate, direct 3–5 words | *"Stop. Obstacle ahead."* |
| **Tier 2 (Navigation)** | Target object or clear path inquiry | Step count & direction | *"The chair is ahead. Take approximately 3 steps forward."* |
| **Tier 3 (Context)** | Weather, Status, Greeting | Concise informational summary | *"Today's weather is 26 degrees Celsius and fair."* |
