import React from "react";
import { SensorTelemetry, VoiceSettings } from "../types";
import { Cpu, Compass, Activity, Navigation, AlertOctagon, RefreshCw, Radio, Sliders, ShieldAlert, Footprints, Layers } from "lucide-react";

interface HardwareTelemetryProps {
  telemetry: SensorTelemetry;
  onUpdateTelemetry: (updates: Partial<SensorTelemetry>) => void;
  voiceSettings: VoiceSettings;
  onUpdateVoiceSettings: (updates: Partial<VoiceSettings>) => void;
  onTriggerFallProtocol: () => void;
  onTriggerOrientationRecovery: () => void;
  onTriggerBriefing: () => void;
}

export const HardwareTelemetry: React.FC<HardwareTelemetryProps> = ({
  telemetry,
  onUpdateTelemetry,
  voiceSettings,
  onUpdateVoiceSettings,
  onTriggerFallProtocol,
  onTriggerOrientationRecovery,
  onTriggerBriefing,
}) => {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl flex flex-col gap-5">
      {/* Top Controller Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
            <Cpu className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
              Sensor Bus & Telemetry Stream
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            </h3>
            <p className="text-xs text-slate-400">Ultrasonic HC-SR04 • MPU6050 Accelerometer • GPS Module</p>
          </div>
        </div>

        {/* AI Engine Selection */}
        <div className="flex items-center bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs">
          <button
            onClick={() => onUpdateVoiceSettings({ onlineMode: true })}
            className={`px-3 py-1 rounded-lg font-medium transition flex items-center gap-1 ${
              voiceSettings.onlineMode
                ? "bg-indigo-600 text-white shadow"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Radio className="w-3.5 h-3.5" />
            Online (Gemini AI Brain)
          </button>
          <button
            onClick={() => onUpdateVoiceSettings({ onlineMode: false })}
            className={`px-3 py-1 rounded-lg font-medium transition flex items-center gap-1 ${
              !voiceSettings.onlineMode
                ? "bg-amber-600 text-white shadow"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Cpu className="w-3.5 h-3.5" />
            Offline (Edge Safety Guard)
          </button>
        </div>
      </div>

      {/* Sensor Grid Displays */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Sensor 1: Ultrasonic Distance Sensor */}
        <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 flex flex-col gap-2">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span className="font-semibold text-slate-200 flex items-center gap-1">
              <Activity className="w-4 h-4 text-emerald-400" /> Ultrasonic HC-SR04
            </span>
            <span
              className={`font-mono text-[11px] font-bold px-2 py-0.5 rounded ${
                telemetry.ultrasonicCm <= 60
                  ? "bg-red-500/20 text-red-300 border border-red-500/40 animate-pulse"
                  : "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
              }`}
            >
              {telemetry.ultrasonicCm <= 60 ? "HAZARD (<60cm)" : "NORMAL"}
            </span>
          </div>

          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-mono font-bold text-slate-100">{telemetry.ultrasonicCm}</span>
            <span className="text-xs text-slate-400 font-mono">cm</span>
            <span className="text-xs text-emerald-400 font-mono ml-auto">
              ≈ {Math.ceil((telemetry.ultrasonicCm / 100) / voiceSettings.stepLengthMeters)} steps
            </span>
          </div>

          <input
            type="range"
            min="10"
            max="200"
            value={telemetry.ultrasonicCm}
            onChange={(e) => onUpdateTelemetry({ ultrasonicCm: parseInt(e.target.value) })}
            className="accent-emerald-500 mt-1 cursor-pointer"
          />
          <div className="flex justify-between text-[10px] font-mono text-slate-500">
            <span>10cm (Stop)</span>
            <span>60cm (Hazard)</span>
            <span>200cm (Clear)</span>
          </div>
        </div>

        {/* Sensor 2: MPU6050 IMU Accelerometer & Gait Steps */}
        <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 flex flex-col gap-2">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span className="font-semibold text-slate-200 flex items-center gap-1">
              <Footprints className="w-4 h-4 text-sky-400" /> MPU6050 Gait Accelerometer
            </span>
            <span className="font-mono text-[11px] text-sky-300">
              SL: {(voiceSettings.stepLengthMeters * 100).toFixed(0)}cm
            </span>
          </div>

          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-mono font-bold text-slate-100">{telemetry.stepCount}</span>
            <span className="text-xs text-slate-400">total steps</span>
          </div>

          <div className="flex items-center gap-2 pt-1">
            <span className="text-[11px] text-slate-400 shrink-0">Calibrate SL:</span>
            <input
              type="range"
              min="0.40"
              max="0.95"
              step="0.05"
              value={voiceSettings.stepLengthMeters}
              onChange={(e) => onUpdateVoiceSettings({ stepLengthMeters: parseFloat(e.target.value) })}
              className="accent-sky-500 w-full cursor-pointer"
            />
            <span className="text-xs font-mono text-slate-200 font-bold">{voiceSettings.stepLengthMeters.toFixed(2)}m</span>
          </div>
        </div>

        {/* Sensor 3: GPS Compass & Orientation */}
        <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 flex flex-col gap-2">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span className="font-semibold text-slate-200 flex items-center gap-1">
              <Compass className="w-4 h-4 text-purple-400" /> GPS & Orientation
            </span>
            <span className="font-mono text-[11px] text-purple-300">{telemetry.compassHeading}</span>
          </div>

          <p className="text-xs text-slate-200 font-medium line-clamp-1">{telemetry.address}</p>
          <p className="text-[11px] text-slate-400 font-mono">
            {telemetry.gpsCoords.lat.toFixed(4)}° N, {telemetry.gpsCoords.lng.toFixed(4)}° E
          </p>
        </div>
      </div>

      {/* Cane Physical Handle Emergency Controls */}
      <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 flex flex-col gap-3">
        <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
          <Sliders className="w-3.5 h-3.5 text-emerald-400" /> Smart Cane Physical Handle Controls
        </h4>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {/* Button 1: Orientation Recovery */}
          <button
            onClick={onTriggerOrientationRecovery}
            className="p-3 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-xl text-left transition flex items-center gap-3 active:scale-95 group"
          >
            <div className="p-2 rounded-lg bg-sky-500/20 text-sky-400 group-hover:bg-sky-500/30">
              <Navigation className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xs font-semibold text-slate-200">Orientation Tap</div>
              <div className="text-[10px] text-slate-400">Tactile Compass Heading</div>
            </div>
          </button>

          {/* Button 2: Ambient Scene Briefing */}
          <button
            onClick={onTriggerBriefing}
            className="p-3 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-xl text-left transition flex items-center gap-3 active:scale-95 group"
          >
            <div className="p-2 rounded-lg bg-emerald-500/20 text-emerald-400 group-hover:bg-emerald-500/30">
              <RefreshCw className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xs font-semibold text-slate-200">Scene Briefing</div>
              <div className="text-[10px] text-slate-400">Verbal Room Overview</div>
            </div>
          </button>

          {/* Button 3: Fall Impact & SOS Trigger */}
          <button
            onClick={onTriggerFallProtocol}
            className="p-3 bg-red-950/40 hover:bg-red-950/60 border border-red-800/60 rounded-xl text-left transition flex items-center gap-3 active:scale-95 group"
          >
            <div className="p-2 rounded-lg bg-red-500/20 text-red-400 group-hover:bg-red-500/30">
              <AlertOctagon className="w-4 h-4 text-red-400" />
            </div>
            <div>
              <div className="text-xs font-semibold text-red-200">Simulate Fall Impact</div>
              <div className="text-[10px] text-red-400/80">30s SOS Countdown</div>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
};
