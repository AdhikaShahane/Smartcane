import React from "react";
import { SystemDiagnosticsReport, DiagnosticItem } from "../core/diagnostics";
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  Laptop,
  Cpu,
  RefreshCw,
  Sparkles,
  ShieldCheck,
  Radio,
  Eye,
  Mic,
  Volume2,
  Globe,
  Activity,
  Layers,
  Unlock,
} from "lucide-react";

interface StartupDiagnosticsPanelProps {
  report: SystemDiagnosticsReport;
  currentMode: "DEVELOPMENT" | "RASPBERRY_PI";
  onModeChange: (mode: "DEVELOPMENT" | "RASPBERRY_PI") => void;
  onRerunDiagnostics: () => void;
  onRequestPermissions: () => void;
  isInitializing: boolean;
}

export const StartupDiagnosticsPanel: React.FC<StartupDiagnosticsPanelProps> = ({
  report,
  currentMode,
  onModeChange,
  onRerunDiagnostics,
  onRequestPermissions,
  isInitializing,
}) => {
  const getCategoryIcon = (category: DiagnosticItem["category"]) => {
    switch (category) {
      case "VISION":
        return <Eye className="w-3.5 h-3.5 text-sky-400" />;
      case "AUDIO":
        return <Volume2 className="w-3.5 h-3.5 text-emerald-400" />;
      case "SPEECH":
        return <Mic className="w-3.5 h-3.5 text-indigo-400" />;
      case "AI":
        return <Sparkles className="w-3.5 h-3.5 text-purple-400" />;
      case "NETWORK":
        return <Globe className="w-3.5 h-3.5 text-amber-400" />;
      case "SENSORS":
        return <Activity className="w-3.5 h-3.5 text-rose-400" />;
    }
  };

  const getStatusBadge = (status: DiagnosticItem["status"]) => {
    switch (status) {
      case "READY":
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-mono font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 px-2 py-0.5 rounded-full">
            <CheckCircle2 className="w-3 h-3 text-emerald-400" /> READY
          </span>
        );
      case "PERMISSION_REQUIRED":
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-mono font-bold text-amber-400 bg-amber-500/10 border border-amber-500/30 px-2 py-0.5 rounded-full animate-pulse">
            <AlertTriangle className="w-3 h-3 text-amber-400" /> PERMISSION REQ
          </span>
        );
      case "CHECKING":
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-mono font-bold text-sky-400 bg-sky-500/10 border border-sky-500/30 px-2 py-0.5 rounded-full">
            <Clock className="w-3 h-3 text-sky-400 animate-spin" /> CHECKING
          </span>
        );
      case "NOT_CONNECTED":
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-mono font-bold text-slate-400 bg-slate-800 border border-slate-700 px-2 py-0.5 rounded-full">
            <XCircle className="w-3 h-3 text-slate-500" /> NOT CONNECTED
          </span>
        );
      case "ERROR":
      default:
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-mono font-bold text-rose-400 bg-rose-500/10 border border-rose-500/30 px-2 py-0.5 rounded-full">
            <XCircle className="w-3 h-3 text-rose-400" /> ERROR
          </span>
        );
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-2xl flex flex-col gap-4">
      {/* Top Header & Mode Switcher */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-indigo-500/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white tracking-wide flex items-center gap-2">
                SmartCane Startup Diagnostics & Hardware Bus
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 uppercase font-bold">
                  {report.allReady ? "ALL SUBSYSTEMS READY" : "DIAGNOSTICS ACTIVE"}
                </span>
              </h2>
              <p className="text-xs text-slate-400">
                Robotic subsystem verification: Camera, Mic, Speech, TTS, AI Vision, Weather & Sensors
              </p>
            </div>
          </div>
        </div>

        {/* Execution Mode Selector (Development vs Raspberry Pi) */}
        <div className="flex items-center gap-2 bg-slate-950 p-1 rounded-xl border border-slate-800 self-stretch sm:self-auto">
          <button
            onClick={() => onModeChange("DEVELOPMENT")}
            className={`flex-1 sm:flex-none px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center justify-center gap-1.5 ${
              currentMode === "DEVELOPMENT"
                ? "bg-sky-600 text-white shadow-lg shadow-sky-900/40"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Laptop className="w-3.5 h-3.5" />
            <span>Development Mode</span>
          </button>

          <button
            onClick={() => onModeChange("RASPBERRY_PI")}
            className={`flex-1 sm:flex-none px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center justify-center gap-1.5 ${
              currentMode === "RASPBERRY_PI"
                ? "bg-purple-600 text-white shadow-lg shadow-purple-900/40"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Cpu className="w-3.5 h-3.5" />
            <span>Raspberry Pi Mode</span>
          </button>
        </div>
      </div>

      {/* Mode Clarification Notice */}
      <div className="bg-slate-950/70 border border-slate-800/80 rounded-xl p-3 flex items-start justify-between gap-3 text-xs">
        <div className="flex items-start gap-2.5">
          <Layers className="w-4 h-4 text-sky-400 mt-0.5 shrink-0" />
          <div className="text-slate-300">
            {currentMode === "DEVELOPMENT" ? (
              <>
                <strong className="text-sky-300">DEVELOPMENT ENVIRONMENT ACTIVE:</strong> Uses Laptop/Desktop USB Webcam,
                Computer Microphone, Web Speech Recognition & SpeechSynthesis, and Simulated MPU6050 Gait Acceleration.
                {report.hasPermissionBlock && (
                  <span className="block mt-1 text-amber-300">
                    ⚠️ Browser security policy requires user authorization to connect camera & microphone streams.
                  </span>
                )}
              </>
            ) : (
              <>
                <strong className="text-purple-300">RASPBERRY PI DEPLOYMENT ARCHITECTURE:</strong> Direct hardware bindings
                via V4L2/Picamera2, ALSA audio input, pyttsx3 / espeak TTS, I2C 0x68 (MPU6050), and GPIO 23/24 (HC-SR04).
                No browser permissions or GUI required for headless operation.
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {report.hasPermissionBlock && (
            <button
              onClick={onRequestPermissions}
              className="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-slate-950 font-bold rounded-lg text-xs transition flex items-center gap-1.5 shadow-lg shadow-amber-900/30 active:scale-95"
            >
              <Unlock className="w-3.5 h-3.5" />
              <span>Authorize Hardware</span>
            </button>
          )}

          <button
            onClick={onRerunDiagnostics}
            disabled={isInitializing}
            className="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg text-xs transition flex items-center gap-1.5 disabled:opacity-50"
            title="Re-test all robotic subsystems"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isInitializing ? "animate-spin" : ""}`} />
            <span className="hidden sm:inline">Re-Run Tests</span>
          </button>
        </div>
      </div>

      {/* Diagnostics Items Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5">
        {report.items.map((item) => (
          <div
            key={item.id}
            className="bg-slate-950 border border-slate-800/90 rounded-xl p-3 flex flex-col justify-between gap-2 hover:border-slate-700 transition"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-center">
                  {getCategoryIcon(item.category)}
                </div>
                <div>
                  <h3 className="text-xs font-semibold text-slate-200">{item.name}</h3>
                  <span className="text-[10px] text-slate-400 font-mono">
                    {item.isHardwareReal ? "REAL HARDWARE" : "SIMULATED / EMULATED"}
                  </span>
                </div>
              </div>
              {getStatusBadge(item.status)}
            </div>

            <div className="text-[11px] text-slate-400 leading-snug">
              {item.details}
              {typeof item.latencyMs === "number" && (
                <span className="block text-[10px] text-slate-400 font-mono mt-0.5">
                  Latency: {item.latencyMs}ms
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
