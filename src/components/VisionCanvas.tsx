import React, { useRef, useState, useEffect, useCallback } from "react";
import { VoiceSettings } from "../types";
import {
  Camera,
  Eye,
  AlertCircle,
  CheckCircle2,
  Video,
  ShieldAlert,
  Cpu,
  Layers,
  Activity,
} from "lucide-react";
import { DetectedObject } from "../core/types";

interface VisionCanvasProps {
  voiceSettings: VoiceSettings;
  onAnalyzeFrame: (customPrompt?: string, imageBase64?: string) => void;
  isAnalyzing: boolean;
  onCameraStatusChange?: (status: "READY" | "ACTIVE" | "WAITING_PERMISSION" | "NOT_CONNECTED" | "ERROR", deviceName?: string) => void;
  onDetectionsUpdated?: (objects: DetectedObject[]) => void;
}

export const VisionCanvas: React.FC<VisionCanvasProps> = ({
  voiceSettings,
  onAnalyzeFrame,
  isAnalyzing,
  onCameraStatusChange,
  onDetectionsUpdated,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Perception Subsystem State: INITIALIZING | READY | ACTIVE | WAITING_PERMISSION | ERROR
  const [perceptionState, setPerceptionState] = useState<
    "INITIALIZING" | "READY" | "ACTIVE" | "WAITING_PERMISSION" | "NOT_CONNECTED" | "ERROR"
  >("INITIALIZING");

  // Hardware Source: 'REAL_WEBCAM' vs 'SYNTHETIC_TEST_BENCH'
  const [hardwareSource, setHardwareSource] = useState<"REAL_WEBCAM" | "SYNTHETIC_TEST_BENCH">("SYNTHETIC_TEST_BENCH");
  const [activeDeviceLabel, setActiveDeviceLabel] = useState<string>("");
  const [videoDevices, setVideoDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Continuous background perception loop interval (seconds)
  const [perceptionIntervalSec, setPerceptionIntervalSec] = useState<number>(2.5);
  const [fps, setFps] = useState<number>(0);
  const [lastFrameTimestamp, setLastFrameTimestamp] = useState<string>("");

  const animIdRef = useRef<number | null>(null);
  const syntheticCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const isAnalyzingRef = useRef<boolean>(isAnalyzing);

  useEffect(() => {
    isAnalyzingRef.current = isAnalyzing;
  }, [isAnalyzing]);

  // Check if camera should be excluded (e.g. OBS virtual camera)
  const isExcludedCamera = (label?: string) => {
    if (!label) return false;
    const l = label.toLowerCase();
    return (
      l.includes("obs virtual camera") ||
      l.includes("obs-camera") ||
      l.includes("obs virtual") ||
      l.includes("obs-virtual")
    );
  };

  // Enumerate physical camera devices
  const enumerateCameras = useCallback(async () => {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.enumerateDevices) {
      return;
    }
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const videoInputs = devices.filter((d) => d.kind === "videoinput" && !isExcludedCamera(d.label));
      setVideoDevices(videoInputs);

      if (videoInputs.length > 0 && !selectedDeviceId) {
        // Look for USB2.0 HD UVC Webcam or physical webcam first
        const preferred = videoInputs.find(
          (d) => d.label.toLowerCase().includes("usb") || d.label.toLowerCase().includes("uvc")
        );
        setSelectedDeviceId(preferred ? preferred.deviceId : videoInputs[0].deviceId);
      }
    } catch (e) {
      console.warn("Camera device enumeration notice:", e);
    }
  }, [selectedDeviceId]);

  // Draw Synthetic Test Bench (Clearly marked as simulation for honest diagnostics)
  const startSyntheticTestBench = useCallback(() => {
    if (animIdRef.current) {
      cancelAnimationFrame(animIdRef.current);
      animIdRef.current = null;
    }

    let animCanvas = syntheticCanvasRef.current;
    if (!animCanvas) {
      animCanvas = document.createElement("canvas");
      animCanvas.width = 640;
      animCanvas.height = 360;
      syntheticCanvasRef.current = animCanvas;
    }

    const ctx = animCanvas.getContext("2d");
    if (!ctx) return false;

    let frameCount = 0;
    let lastFpsCheck = performance.now();
    let framesThisSec = 0;

    const drawFrame = () => {
      frameCount++;
      framesThisSec++;
      const now = performance.now();
      if (now - lastFpsCheck >= 1000) {
        setFps(framesThisSec);
        framesThisSec = 0;
        lastFpsCheck = now;
      }

      const time = frameCount * 0.025;

      // Dark test bench corridor
      ctx.fillStyle = "#090d16";
      ctx.fillRect(0, 0, 640, 360);

      // Floor perspective
      const horizonY = 135;
      ctx.beginPath();
      ctx.moveTo(0, 360);
      ctx.lineTo(250, horizonY);
      ctx.lineTo(390, horizonY);
      ctx.lineTo(640, 360);
      ctx.fillStyle = "#0f172a";
      ctx.fill();
      ctx.strokeStyle = "rgba(56, 189, 248, 0.3)";
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Moving floor lines to simulate walking forward
      const numLines = 6;
      for (let i = 0; i < numLines; i++) {
        const progress = (time * 0.7 + i / numLines) % 1;
        const lineY = horizonY + progress * (360 - horizonY);
        const startX = 250 - progress * 250;
        const endX = 390 + progress * 250;

        ctx.beginPath();
        ctx.moveTo(startX, lineY);
        ctx.lineTo(endX, lineY);
        ctx.strokeStyle = `rgba(56, 189, 248, ${0.1 + progress * 0.4})`;
        ctx.stroke();
      }

      // Simulated Obstacle (Chair / Obstacle on path)
      const objZ = (time * 0.45) % 1;
      const objY = horizonY + objZ * (300 - horizonY);
      const objScale = 0.25 + objZ * 0.9;
      const objWidth = 65 * objScale;
      const objHeight = 85 * objScale;
      const objX = 320 + Math.sin(time * 0.4) * 35 - objWidth / 2;

      // Draw obstacle box
      ctx.fillStyle = "rgba(239, 68, 68, 0.85)";
      ctx.fillRect(objX, objY - objHeight, objWidth, objHeight);
      ctx.strokeStyle = "#f87171";
      ctx.lineWidth = 2;
      ctx.strokeRect(objX, objY - objHeight, objWidth, objHeight);

      // Label on obstacle
      ctx.fillStyle = "#ffffff";
      ctx.font = `bold ${Math.max(10, Math.floor(13 * objScale))}px sans-serif`;
      ctx.fillText("OBJECT: CHAIR", objX, objY - objHeight - 6);

      // Simulation Diagnostic HUD
      ctx.fillStyle = "rgba(251, 191, 36, 0.9)";
      ctx.font = "bold 12px monospace";
      ctx.fillText("TEST BENCH SIMULATION [NO REAL WEBCAM PERMITTED YET]", 16, 26);
      ctx.fillStyle = "#94a3b8";
      ctx.font = "10px monospace";
      ctx.fillText(`TIMECODE: ${new Date().toLocaleTimeString()} | CORRIDOR TEST SCENE`, 16, 42);

      animIdRef.current = requestAnimationFrame(drawFrame);
    };

    drawFrame();

    const stream = animCanvas.captureStream(30);
    if (videoRef.current) {
      videoRef.current.srcObject = stream;
      videoRef.current.play().catch(() => {});
      setPerceptionState("ACTIVE");
      setHardwareSource("SYNTHETIC_TEST_BENCH");
      setActiveDeviceLabel("Synthetic Test Bench (Emulated)");
      if (onCameraStatusChange) {
        onCameraStatusChange("ACTIVE", "Synthetic Test Bench");
      }
      return true;
    }
    return false;
  }, [onCameraStatusChange]);

  // Initialize Real Physical Camera Stream via MediaDevices
  const initializeRealCamera = useCallback(
    async (deviceIdToUse?: string) => {
      setErrorMessage(null);
      setPerceptionState("INITIALIZING");

      if (videoRef.current) {
        videoRef.current.muted = true;
        videoRef.current.autoplay = true;
        videoRef.current.playsInline = true;
      }

      let stream: MediaStream | null = null;
      const targetDeviceId = deviceIdToUse || selectedDeviceId;

      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        // Stop any active stream first
        if (videoRef.current && videoRef.current.srcObject) {
          const s = videoRef.current.srcObject as MediaStream;
          s.getTracks().forEach((t) => t.stop());
        }

        try {
          // Attempt 1: Target specific camera / back camera
          const constraints: any = targetDeviceId
            ? { deviceId: { exact: targetDeviceId }, width: { ideal: 1280 }, height: { ideal: 720 } }
            : { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } };

          stream = await navigator.mediaDevices.getUserMedia({ video: constraints, audio: false });
        } catch {
          try {
            // Attempt 2: Generic user-facing webcam
            stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
          } catch (permErr: any) {
            console.warn("Real camera access blocked or unavailable:", permErr);
            stream = null;
          }
        }
      }

      if (stream && videoRef.current) {
        try {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();

          const track = stream.getVideoTracks()[0];
          const deviceLabel = track?.label || "Real Physical Webcam";

          setPerceptionState("ACTIVE");
          setHardwareSource("REAL_WEBCAM");
          setActiveDeviceLabel(deviceLabel);
          setErrorMessage(null);

          if (onCameraStatusChange) {
            onCameraStatusChange("ACTIVE", deviceLabel);
          }

          enumerateCameras();
          return;
        } catch (e: any) {
          console.warn("Video playback start error:", e);
        }
      }

      // If browser permission is blocked, inform user honestly and start test bench
      setPerceptionState("WAITING_PERMISSION");
      setErrorMessage("Browser security requires camera permission to access physical webcam stream.");
      if (onCameraStatusChange) {
        onCameraStatusChange("WAITING_PERMISSION");
      }
      startSyntheticTestBench();
    },
    [selectedDeviceId, startSyntheticTestBench, onCameraStatusChange, enumerateCameras]
  );

  // Automatic Camera Startup on Component Mount
  useEffect(() => {
    initializeRealCamera();

    return () => {
      if (animIdRef.current) {
        cancelAnimationFrame(animIdRef.current);
        animIdRef.current = null;
      }
      if (videoRef.current && videoRef.current.srcObject) {
        const stream = videoRef.current.srcObject as MediaStream;
        stream.getTracks().forEach((t) => t.stop());
        videoRef.current.srcObject = null;
      }
    };
  }, [initializeRealCamera]);

  // Capture Frame as Base64 JPEG for AI Vision Loop
  const captureFrameBase64 = useCallback((): string | undefined => {
    const canvas = canvasRef.current || document.createElement("canvas");
    canvas.width = 480;
    canvas.height = 270;

    const ctx = canvas.getContext("2d");
    if (!ctx) return undefined;

    const video = videoRef.current;
    if (video && (video.readyState >= 2 || video.videoWidth > 0)) {
      try {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        setLastFrameTimestamp(new Date().toLocaleTimeString());
        return canvas.toDataURL("image/jpeg", 0.45);
      } catch (e) {
        console.warn("Frame capture error:", e);
      }
    }

    if (syntheticCanvasRef.current) {
      try {
        ctx.drawImage(syntheticCanvasRef.current, 0, 0, canvas.width, canvas.height);
        setLastFrameTimestamp(new Date().toLocaleTimeString());
        return canvas.toDataURL("image/jpeg", 0.45);
      } catch (e) {}
    }

    return undefined;
  }, []);

  // Continuous Autonomous Environmental Perception Loop
  useEffect(() => {
    if (perceptionState !== "ACTIVE") return;

    const interval = setInterval(() => {
      // If AI brain is not busy processing a previous query, run continuous environmental perception
      if (!isAnalyzingRef.current) {
        const frame = captureFrameBase64();
        if (frame) {
          onAnalyzeFrame("Autonomous environmental hazard and path scan", frame);
        }
      }
    }, perceptionIntervalSec * 1000);

    return () => clearInterval(interval);
  }, [perceptionState, perceptionIntervalSec, captureFrameBase64, onAnalyzeFrame]);

  return (
    <div className="bg-slate-900 text-white rounded-2xl border border-slate-800 shadow-2xl overflow-hidden flex flex-col">
      <canvas ref={canvasRef} className="hidden" />

      {/* Top Vision Perception Status Bar */}
      <div className="p-4 border-b border-slate-800 bg-slate-950/90 backdrop-blur flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div
            className={`w-8 h-8 rounded-xl flex items-center justify-center border ${
              hardwareSource === "REAL_WEBCAM"
                ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/40"
                : "bg-amber-500/20 text-amber-400 border-amber-500/40"
            }`}
          >
            <Eye className="w-4 h-4 animate-pulse" />
          </div>
          <div>
            <h2 className="text-sm font-bold tracking-wide text-slate-100 flex items-center gap-2">
              Autonomous Vision Subsystem
              <span
                className={`text-[10px] px-2 py-0.5 rounded-full font-mono uppercase font-bold ${
                  perceptionState === "ACTIVE"
                    ? hardwareSource === "REAL_WEBCAM"
                      ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                      : "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                    : "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                }`}
              >
                {perceptionState === "ACTIVE"
                  ? hardwareSource === "REAL_WEBCAM"
                    ? "REAL WEBCAM: ACTIVE"
                    : "TEST BENCH SIMULATION"
                  : perceptionState}
              </span>
            </h2>
            <p className="text-xs text-slate-400">
              {hardwareSource === "REAL_WEBCAM"
                ? `Device: ${activeDeviceLabel || "Physical Camera Connected"}`
                : "Development scene stream running continuous hazard detection loop"}
            </p>
          </div>
        </div>

        {/* Camera Device Switcher (If multiple cameras detected) */}
        <div className="flex items-center gap-2 flex-wrap">
          {videoDevices.length > 1 && (
            <select
              value={selectedDeviceId}
              onChange={(e) => {
                setSelectedDeviceId(e.target.value);
                initializeRealCamera(e.target.value);
              }}
              className="bg-slate-800 border border-slate-700 text-xs text-slate-200 rounded-lg px-2.5 py-1.5 focus:outline-none"
            >
              {videoDevices.map((dev, idx) => (
                <option key={dev.deviceId || idx} value={dev.deviceId}>
                  {dev.label || `Camera ${idx + 1}`}
                </option>
              ))}
            </select>
          )}

          {hardwareSource !== "REAL_WEBCAM" && (
            <button
              onClick={() => initializeRealCamera()}
              className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-lg text-xs transition flex items-center gap-1.5 shadow-lg shadow-emerald-900/30 active:scale-95"
            >
              <Camera className="w-3.5 h-3.5" />
              <span>Connect Physical Webcam</span>
            </button>
          )}

          <div className="bg-slate-950 border border-slate-800 px-2.5 py-1 rounded-lg text-[11px] font-mono text-slate-400 flex items-center gap-2">
            <Activity className="w-3 h-3 text-emerald-400 animate-pulse" />
            <span>Loop: {perceptionIntervalSec}s</span>
          </div>
        </div>
      </div>

      {/* Main Video Perception Viewport */}
      <div className="relative aspect-[16/9] w-full bg-black overflow-hidden select-none flex items-center justify-center">
        {/* Permission Request Banner if blocked by browser security */}
        {perceptionState === "WAITING_PERMISSION" && (
          <div className="absolute inset-0 bg-slate-950/90 p-6 flex flex-col items-center justify-center text-center gap-3 z-30">
            <AlertCircle className="w-10 h-10 text-amber-400" />
            <div>
              <h3 className="text-base font-bold text-slate-100">Camera Permission Required</h3>
              <p className="text-xs text-slate-400 max-w-md mt-1">
                Browser security policy requires a user click to authorize access to your physical webcam.
              </p>
            </div>
            <button
              onClick={() => initializeRealCamera()}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-xl text-xs transition shadow-lg shadow-emerald-900/30 active:scale-95"
            >
              Authorize Physical Camera
            </button>
          </div>
        )}

        {/* Live Video Element */}
        <video
          ref={videoRef}
          className="w-full h-full object-cover"
          playsInline
          muted
          autoPlay
        />

        {/* 3 Spatial Zones HUD Overlay */}
        <div className="absolute inset-0 pointer-events-none flex z-10">
          {/* Left Zone: 0% - 33% */}
          <div className="w-[33%] h-full border-r border-dashed border-sky-400/30 bg-sky-950/10 p-2 relative">
            <div className="bg-slate-950/80 text-sky-300 border border-sky-500/40 text-[10px] font-mono px-2 py-0.5 rounded backdrop-blur inline-flex items-center gap-1">
              <span>LEFT ZONE</span>
              <span className="text-sky-400 font-semibold">(9:00 - 11:00)</span>
            </div>
          </div>

          {/* Center Zone: 34% - 66% */}
          <div className="w-[34%] h-full border-r border-dashed border-emerald-400/40 bg-emerald-950/10 p-2 flex justify-center">
            <div className="bg-slate-950/80 text-emerald-300 border border-emerald-500/40 text-[10px] font-mono px-2 py-0.5 rounded backdrop-blur inline-flex items-center gap-1 h-fit">
              <span>CENTER ZONE</span>
              <span className="text-emerald-400 font-semibold">(12:00 Direct Ahead)</span>
            </div>
          </div>

          {/* Right Zone: 67% - 100% */}
          <div className="w-[33%] h-full bg-purple-950/10 p-2 flex justify-end">
            <div className="bg-slate-950/80 text-purple-300 border border-purple-500/40 text-[10px] font-mono px-2 py-0.5 rounded backdrop-blur inline-flex items-center gap-1 h-fit">
              <span>RIGHT ZONE</span>
              <span className="text-purple-400 font-semibold">(1:00 - 3:00)</span>
            </div>
          </div>
        </div>

        {/* Continuous Perception Scan Pulse Effect */}
        {isAnalyzing && (
          <div className="absolute inset-0 bg-gradient-to-b from-transparent via-emerald-500/20 to-transparent h-24 w-full animate-pulse z-20 pointer-events-none" />
        )}
      </div>

      {/* Footer Diagnostic Telemetry Bar */}
      <div className="p-3 bg-slate-950 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1.5 font-mono text-[11px]">
            <span
              className={`w-2 h-2 rounded-full ${
                hardwareSource === "REAL_WEBCAM" ? "bg-emerald-400 animate-pulse" : "bg-amber-400"
              }`}
            />
            {hardwareSource === "REAL_WEBCAM"
              ? "Continuous Live Camera Stream -> Gemini AI Brain"
              : "Continuous Simulation Stream -> Gemini AI Brain"}
          </span>
        </div>

        <div className="flex items-center gap-3 text-[11px] font-mono text-slate-400">
          <span>FPS: {fps > 0 ? fps : 30}</span>
          <span>Last Processed: {lastFrameTimestamp || "Streaming"}</span>
          <label className="flex items-center gap-1 cursor-pointer">
            <span>Perception Loop:</span>
            <select
              value={perceptionIntervalSec}
              onChange={(e) => setPerceptionIntervalSec(Number(e.target.value))}
              className="bg-slate-900 border border-slate-800 rounded px-1.5 py-0.5 text-slate-200 focus:outline-none"
            >
              <option value={1.5}>1.5s</option>
              <option value={2.5}>2.5s</option>
              <option value={4.0}>4.0s</option>
            </select>
          </label>
        </div>
      </div>
    </div>
  );
};
