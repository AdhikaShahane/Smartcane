import React, { useState } from "react";
import { X, Terminal, Cpu, HardDrive, Check, Copy, Shield, BookOpen, Layers } from "lucide-react";

interface RaspberryPiDeploymentModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const RaspberryPiDeploymentModal: React.FC<RaspberryPiDeploymentModalProps> = ({
  isOpen,
  onClose
}) => {
  const [copiedId, setCopiedId] = useState<string | null>(null);

  if (!isOpen) return null;

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const systemdCommand = `sudo nano /etc/systemd/system/smartcane.service
# Paste smartcane_pi/smartcane.service content
sudo systemctl daemon-reload
sudo systemctl enable smartcane.service
sudo systemctl start smartcane.service`;

  const installCommand = `sudo apt update && sudo apt install -y python3-pip python3-smbus i2c-tools python3-rpi.gpio espeak ffmpeg libportaudio2
cd ~ && mkdir smartcane && cd smartcane
pip3 install -r requirements.txt --break-system-packages`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-sm animate-fadeIn">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-3xl max-h-[90vh] flex flex-col shadow-2xl text-slate-100 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-purple-500/10 border border-purple-500/30 text-purple-400">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-100">
                Raspberry Pi Deployment & Hardware Blueprint
              </h2>
              <p className="text-xs text-slate-400">
                Standalone Headless Robotic Service (Raspberry Pi OS Bookworm 64-bit)
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex flex-col gap-6 text-sm">
          {/* Section 1: Hardware Pinouts & Wiring */}
          <div className="flex flex-col gap-2.5">
            <h3 className="text-xs font-bold font-mono text-purple-300 uppercase tracking-wider flex items-center gap-2">
              <HardDrive className="w-4 h-4 text-purple-400" />
              1. Hardware Wiring & Pinout Guide
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-3.5 flex flex-col gap-1.5">
                <span className="text-xs font-bold text-amber-400">MPU6050 Accelerometer</span>
                <p className="text-[11px] text-slate-400">Calculates stride formula: SL = K * ⁴√(a_max − a_min)</p>
                <div className="text-[11px] font-mono text-slate-300 bg-slate-900/90 p-2 rounded border border-slate-800 mt-1">
                  VCC → 3.3V (Pin 1)<br/>
                  GND → GND (Pin 6)<br/>
                  SDA → GPIO 2 (Pin 3)<br/>
                  SCL → GPIO 3 (Pin 5)
                </div>
              </div>

              <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-3.5 flex flex-col gap-1.5">
                <span className="text-xs font-bold text-cyan-400">HC-SR04 Ultrasonic</span>
                <p className="text-[11px] text-slate-400">Immediate collision safety barrier (&lt;0.6m STOP)</p>
                <div className="text-[11px] font-mono text-slate-300 bg-slate-900/90 p-2 rounded border border-slate-800 mt-1">
                  VCC → 5V (Pin 2)<br/>
                  GND → GND (Pin 9)<br/>
                  TRIG → GPIO 23 (Pin 16)<br/>
                  ECHO → GPIO 24 (Pin 18)*
                </div>
                <span className="text-[9px] text-slate-500">*Use 1k/2k voltage divider on Echo</span>
              </div>

              <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-3.5 flex flex-col gap-1.5">
                <span className="text-xs font-bold text-emerald-400">Camera & Audio</span>
                <p className="text-[11px] text-slate-400">Vision eyes & voice input/output</p>
                <div className="text-[11px] font-mono text-slate-300 bg-slate-900/90 p-2 rounded border border-slate-800 mt-1">
                  Camera → CSI Ribon / USB UVC<br/>
                  Mic → USB / I2S Mic<br/>
                  Speaker → 3.5mm / I2S Amp<br/>
                  GPS → UART (/dev/ttyS0)
                </div>
              </div>
            </div>
          </div>

          {/* Section 2: Quick Terminal Installation */}
          <div className="flex flex-col gap-2.5">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold font-mono text-purple-300 uppercase tracking-wider flex items-center gap-2">
                <Terminal className="w-4 h-4 text-purple-400" />
                2. Install Dependencies on Raspberry Pi
              </h3>
              <button
                onClick={() => copyToClipboard(installCommand, "install")}
                className="px-2.5 py-1 text-xs bg-slate-800 hover:bg-slate-700 rounded-lg text-slate-300 border border-slate-700 flex items-center gap-1.5 transition"
              >
                {copiedId === "install" ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                {copiedId === "install" ? "Copied" : "Copy Command"}
              </button>
            </div>
            <pre className="p-3 bg-slate-950 rounded-xl border border-slate-800 font-mono text-xs text-emerald-400 overflow-x-auto">
              {installCommand}
            </pre>
          </div>

          {/* Section 3: Enable Background System Service */}
          <div className="flex flex-col gap-2.5">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold font-mono text-purple-300 uppercase tracking-wider flex items-center gap-2">
                <Shield className="w-4 h-4 text-purple-400" />
                3. Enable Auto-Start Background Systemd Service
              </h3>
              <button
                onClick={() => copyToClipboard(systemdCommand, "service")}
                className="px-2.5 py-1 text-xs bg-slate-800 hover:bg-slate-700 rounded-lg text-slate-300 border border-slate-700 flex items-center gap-1.5 transition"
              >
                {copiedId === "service" ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                {copiedId === "service" ? "Copied" : "Copy Command"}
              </button>
            </div>
            <pre className="p-3 bg-slate-950 rounded-xl border border-slate-800 font-mono text-xs text-sky-400 overflow-x-auto">
              {systemdCommand}
            </pre>
          </div>

          {/* Section 4: Included Files Summary */}
          <div className="bg-slate-950/60 rounded-xl p-4 border border-slate-800 flex flex-col gap-2">
            <h4 className="text-xs font-bold text-slate-200 flex items-center gap-2">
              <BookOpen className="w-4 h-4 text-amber-400" />
              Embedded Autonomous Robotic Files Created in Project:
            </h4>
            <ul className="text-xs text-slate-400 space-y-1 font-mono">
              <li>• <code className="text-amber-300">smartcane_pi/smartcane_service.py</code>: Autonomous robotic service running speech, vision, MPU6050 & HC-SR04 loops.</li>
              <li>• <code className="text-amber-300">smartcane_pi/calibrate_k.py</code>: Interactive terminal wizard to calibrate stride constant K.</li>
              <li>• <code className="text-amber-300">smartcane_pi/smartcane.service</code>: Linux systemd unit for headless auto-start on Raspberry Pi boot.</li>
              <li>• <code className="text-amber-300">smartcane_pi/requirements.txt</code>: Python sensor and vision dependencies.</li>
            </ul>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between">
          <span className="text-xs text-slate-400">
            Supports both Dev Mode (browser simulation) and Real Raspberry Pi hardware mode.
          </span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-white font-medium rounded-lg text-xs transition"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};
