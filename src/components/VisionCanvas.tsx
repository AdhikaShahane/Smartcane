import React, { useRef, useState, useEffect, useCallback } from "react";
import { VoiceSettings } from "../types";
import { Camera, Eye, RefreshCw, Sparkles, Video, AlertCircle, Radio } from "lucide-react";

interface VisionCanvasProps {
  voiceSettings: VoiceSettings;
  onAnalyzeFrame: (customPrompt?: string, imageBase64?: string) => void;
  isAnalyzing: boolean;
}

export const VisionCanvas: React.FC<VisionCanvasProps> = ({
  voiceSettings,
  onAnalyzeFrame,
  isAnalyzing,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const [streamActive, setStreamActive] = useState<boolean>(false);
  const [streamMode, setStreamMode] = useState<"hardware" | "synthetic">("hardware");
  const [streamError, setStreamError] = useState<string | null>(null);
  const [autoScan, setAutoScan] = useState<boolean>(false);
  const [scanIntervalSeconds, setScanIntervalSeconds] = useState<number>(5);

  const [videoDevices, setVideoDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>("");

  const animIdRef = useRef<number | null>(null);
  const syntheticCanvasRef = useRef<HTMLCanvasElement | null>(null);

  // Helper to check if a camera device should be excluded (e.g. OBS Virtual Camera)
  const isExcludedCamera = (label?: string) => {
    if (!label) return false;
    const l = label.toLowerCase();
    return (
      l.includes("obs virtual camera") ||
      l.includes("obs-camera") ||
      l.includes("obs virtual") ||
      l.includes("obs-virtual") ||
      l.includes("obs ") ||
      l.startsWith("obs")
    );
  };

  // Enumerate all available camera devices
  const enumerateCameras = useCallback(async () => {
    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const allVideoInputs = devices.filter((d) => d.kind === "videoinput");
        // Filter out OBS virtual cameras, keep physical cameras like USB2.0 HD UVC Webcam
        const filteredCameras = allVideoInputs.filter((d) => !isExcludedCamera(d.label));
        setVideoDevices(filteredCameras);
        if (filteredCameras.length > 0) {
          // If USB2.0 HD UVC Webcam is found and no specific device selected yet, prioritize it
          const usbCam = filteredCameras.find(
            (c) => c.label && (c.label.toLowerCase().includes("usb2.0") || c.label.toLowerCase().includes("uvc"))
          );
          if (!selectedDeviceId || !filteredCameras.some((c) => c.deviceId === selectedDeviceId)) {
            setSelectedDeviceId(usbCam ? usbCam.deviceId : filteredCameras[0].deviceId);
          }
        } else if (allVideoInputs.length === 0) {
          setVideoDevices([]);
        }
      } catch (e) {
        console.warn("Could not enumerate camera devices:", e);
      }
    }
  }, [selectedDeviceId]);

  useEffect(() => {
    enumerateCameras();
  }, [enumerateCameras]);

  // Function to start synthetic animated camera stream as automatic fallback
  const startSyntheticCameraStream = useCallback(() => {
    try {
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

      const drawFrame = () => {
        frameCount++;
        const time = frameCount * 0.03;

        // Background indoor/outdoor hallway environment simulation
        ctx.fillStyle = "#090d16";
        ctx.fillRect(0, 0, 640, 360);

        // Perspective grid lines (hallway floor)
        ctx.strokeStyle = "rgba(56, 189, 248, 0.25)";
        ctx.lineWidth = 1.5;
        const horizonY = 140;

        // Perspective floor
        ctx.beginPath();
        ctx.moveTo(0, 360);
        ctx.lineTo(260, horizonY);
        ctx.lineTo(380, horizonY);
        ctx.lineTo(640, 360);
        ctx.fillStyle = "#0f172a";
        ctx.fill();
        ctx.stroke();

        // Moving floor grid lines to simulate walking forward
        const numLines = 6;
        for (let i = 0; i < numLines; i++) {
          const progress = ((time * 0.8 + i / numLines) % 1);
          const lineY = horizonY + progress * (360 - horizonY);
          const startX = 260 - progress * 260;
          const endX = 380 + progress * 260;

          ctx.beginPath();
          ctx.moveTo(startX, lineY);
          ctx.lineTo(endX, lineY);
          ctx.strokeStyle = `rgba(56, 189, 248, ${0.1 + progress * 0.4})`;
          ctx.stroke();
        }

        // Simulated obstacle object in center (e.g. walking path marker)
        const objZ = ((time * 0.5) % 1);
        const objY = horizonY + objZ * (300 - horizonY);
        const objScale = 0.2 + objZ * 0.9;
        const objWidth = 60 * objScale;
        const objHeight = 80 * objScale;
        const objX = 320 + Math.sin(time * 0.5) * 40 - objWidth / 2;

        ctx.fillStyle = "rgba(239, 68, 68, 0.85)";
        ctx.fillRect(objX, objY - objHeight, objWidth, objHeight);
        ctx.strokeStyle = "#f87171";
        ctx.lineWidth = 2;
        ctx.strokeRect(objX, objY - objHeight, objWidth, objHeight);

        // Simulated text marker on object
        ctx.fillStyle = "#ffffff";
        ctx.font = `bold ${Math.max(10, Math.floor(12 * objScale))}px sans-serif`;
        ctx.fillText("HAZARD: CHAIR", objX, objY - objHeight - 8);

        // HUD overlay text on feed
        ctx.fillStyle = "rgba(16, 185, 129, 0.9)";
        ctx.font = "bold 13px monospace";
        ctx.fillText("LIVE VISION FEED [SIMULATED CAM]", 20, 30);
        ctx.fillStyle = "#94a3b8";
        ctx.font = "11px monospace";
        ctx.fillText(`FPS: 30 | TIMESTAMP: ${new Date().toLocaleTimeString()}`, 20, 48);

        animIdRef.current = requestAnimationFrame(drawFrame);
      };

      drawFrame();

      const stream = animCanvas.captureStream(30);
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.play().catch(() => {});
        setStreamActive(true);
        setStreamMode("synthetic");
        setStreamError(null);
        return true;
      }
    } catch (e) {
      console.warn("Synthetic stream creation failed:", e);
    }
    return false;
  }, []);

  // Function to initialize persistent camera stream via MediaDevices API with fallbacks
  const startCameraStream = useCallback(async (deviceIdToUse?: string) => {
    setStreamError(null);

    if (videoRef.current) {
      videoRef.current.muted = true;
      videoRef.current.autoplay = true;
      videoRef.current.playsInline = true;
    }

    let stream: MediaStream | null = null;

    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      // Stop existing tracks if any
      if (videoRef.current && videoRef.current.srcObject) {
        const currentStream = videoRef.current.srcObject as MediaStream;
        currentStream.getTracks().forEach((t) => t.stop());
      }

      const targetDeviceId = deviceIdToUse || selectedDeviceId;

      // Tier 1: Try specific device or back camera
      try {
        const videoConstraints: any = targetDeviceId
          ? { deviceId: { exact: targetDeviceId } }
          : { facingMode: { ideal: "environment" } };

        stream = await navigator.mediaDevices.getUserMedia({
          video: videoConstraints,
          audio: false,
        });
      } catch {
        try {
          // Tier 2: Try front user camera
          stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "user" },
            audio: false,
          });
        } catch {
          try {
            // Tier 3: Basic generic video
            stream = await navigator.mediaDevices.getUserMedia({
              video: true,
              audio: false,
            });
          } catch {
            stream = null;
          }
        }
      }
    }

    if (stream && videoRef.current) {
      try {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        setStreamActive(true);
        setStreamMode("hardware");
        setStreamError(null);
        enumerateCameras();
        return;
      } catch {
        // Fall through to synthetic stream
      }
    }

    // Auto-fallback to live synthetic camera feed
    const syntheticSuccess = startSyntheticCameraStream();
    if (!syntheticSuccess) {
      setStreamActive(false);
      setStreamError(
        "Camera hardware not detected or permissions blocked. Click 'Connect Camera & Retry' or open app in a new tab."
      );
    }
  }, [selectedDeviceId, startSyntheticCameraStream, enumerateCameras]);

  const stopCameraStream = useCallback(() => {
    if (animIdRef.current) {
      cancelAnimationFrame(animIdRef.current);
      animIdRef.current = null;
    }
    if (videoRef.current && videoRef.current.srcObject) {
      const stream = videoRef.current.srcObject as MediaStream;
      stream.getTracks().forEach((track) => track.stop());
      videoRef.current.srcObject = null;
    }
    setStreamActive(false);
    setAutoScan(false);
  }, []);

  // Auto start camera stream on component mount
  useEffect(() => {
    startCameraStream();

    return () => {
      stopCameraStream();
    };
  }, [startCameraStream, stopCameraStream]);

  // Capture frame from video element as lightweight JPEG base64
  const captureFrameBase64 = (): string | undefined => {
    const canvas = canvasRef.current || document.createElement("canvas");
    canvas.width = 480;
    canvas.height = 270;

    const ctx = canvas.getContext("2d");
    if (!ctx) return undefined;

    const video = videoRef.current;
    if (video && (video.readyState >= 2 || video.videoWidth > 0)) {
      try {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        return canvas.toDataURL("image/jpeg", 0.40);
      } catch (e) {
        console.warn("Video frame draw error:", e);
      }
    }

    // Fallback to synthetic canvas if available
    if (syntheticCanvasRef.current) {
      try {
        ctx.drawImage(syntheticCanvasRef.current, 0, 0, canvas.width, canvas.height);
        return canvas.toDataURL("image/jpeg", 0.40);
      } catch (e) {
        console.warn("Synthetic frame draw error:", e);
      }
    }

    return undefined;
  };

  // Trigger manual scan with live frame captured from camera stream
  const handleTriggerScan = (prompt?: string) => {
    const frameBase64 = captureFrameBase64();
    onAnalyzeFrame(prompt, frameBase64);
  };

  // Periodic continuous auto-scan handler
  useEffect(() => {
    if (!autoScan || !streamActive) return;

    const interval = setInterval(() => {
      if (!isAnalyzing) {
        const frameBase64 = captureFrameBase64();
        onAnalyzeFrame("Continuous environmental navigation scan", frameBase64);
      }
    }, scanIntervalSeconds * 1000);

    return () => clearInterval(interval);
  }, [autoScan, streamActive, isAnalyzing, scanIntervalSeconds, onAnalyzeFrame]);

  return (
    <div className="bg-slate-900 text-white rounded-2xl border border-slate-800 shadow-2xl overflow-hidden flex flex-col">
      {/* Hidden elements */}
      <canvas ref={canvasRef} className="hidden" />

      {/* Top Controls Bar */}
      <div className="p-4 border-b border-slate-800 bg-slate-950/80 backdrop-blur flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
            <Eye className="w-4 h-4 animate-pulse" />
          </div>
          <div>
            <h2 className="text-sm font-semibold tracking-wide text-slate-100 flex items-center gap-2">
              Sahayak Drishti Vision Feed
              <span
                className={`text-[10px] px-2 py-0.5 rounded-full font-mono uppercase font-bold ${
                  streamActive
                    ? streamMode === "hardware"
                      ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                      : "bg-sky-500/20 text-sky-300 border border-sky-500/40"
                    : "bg-red-500/20 text-red-300 border border-red-500/40"
                }`}
              >
                {streamActive
                  ? streamMode === "hardware"
                    ? "CAMERA ONLINE"
                    : "SIMULATED FEED"
                  : "STREAM OFF"}
              </span>
            </h2>
            <p className="text-xs text-slate-400">Piping live camera feed directly to Gemini 3.6 AI</p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Camera Selector Dropdown (if multiple video inputs exist) */}
          {videoDevices.length > 1 && (
            <select
              value={selectedDeviceId}
              onChange={(e) => {
                setSelectedDeviceId(e.target.value);
                startCameraStream(e.target.value);
              }}
              className="bg-slate-800 border border-slate-700 text-xs text-slate-200 rounded-lg px-2 py-1.5 focus:outline-none"
            >
              {videoDevices.map((dev, idx) => (
                <option key={dev.deviceId || idx} value={dev.deviceId}>
                  {dev.label || `Camera ${idx + 1}`}
                </option>
              ))}
            </select>
          )}

          {/* Stream Start/Stop Toggle */}
          <button
            onClick={streamActive ? stopCameraStream : () => startCameraStream()}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg border transition flex items-center gap-1.5 ${
              streamActive
                ? "bg-red-500/10 hover:bg-red-500/20 text-red-300 border-red-500/30"
                : "bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
            }`}
          >
            <Camera className="w-3.5 h-3.5" />
            {streamActive ? "Stop Feed" : "Start Camera"}
          </button>

          {/* Continuous Auto-Scan Toggle */}
          <button
            onClick={() => setAutoScan(!autoScan)}
            disabled={!streamActive}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg border transition flex items-center gap-1.5 disabled:opacity-50 ${
              autoScan
                ? "bg-indigo-600 text-white border-indigo-500 animate-pulse"
                : "bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700"
            }`}
          >
            <Radio className="w-3.5 h-3.5" />
            {autoScan ? "Auto-Scan ON" : "Auto-Scan OFF"}
          </button>

          {/* Manual Scan Button */}
          <button
            onClick={() => handleTriggerScan()}
            disabled={isAnalyzing || !streamActive}
            className="px-3.5 py-1.5 text-xs font-medium rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/30 transition flex items-center gap-1.5 disabled:opacity-50"
          >
            {isAnalyzing ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Sparkles className="w-3.5 h-3.5 text-emerald-200" />
            )}
            {isAnalyzing ? "Analyzing..." : "Scan & Brief"}
          </button>
        </div>
      </div>

      {/* Main Stream Viewport */}
      <div className="relative aspect-[16/9] w-full bg-black overflow-hidden select-none flex items-center justify-center">
        {/* Stream Error Notice */}
        {streamError && (
          <div className="absolute inset-0 bg-slate-950/95 p-6 flex flex-col items-center justify-center text-center gap-3 z-30">
            <AlertCircle className="w-10 h-10 text-amber-400" />
            <div>
              <h3 className="text-base font-bold text-slate-100">Camera Access Notice</h3>
              <p className="text-xs text-slate-400 max-w-md mt-1">{streamError}</p>
            </div>
            <div className="flex flex-wrap items-center justify-center gap-2 mt-2">
              <button
                onClick={() => startCameraStream()}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-medium rounded-xl text-xs transition shadow-lg shadow-emerald-900/30"
              >
                Connect Camera & Retry
              </button>
              <a
                href={window.location.href}
                target="_blank"
                rel="noreferrer"
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-medium rounded-xl text-xs transition inline-flex items-center gap-1"
              >
                Open in New Tab ↗
              </a>
            </div>
          </div>
        )}

        {/* Live Video Feed Element */}
        <video
          ref={videoRef}
          className={`w-full h-full object-cover transition-opacity duration-300 ${
            streamActive ? "opacity-100" : "opacity-0 hidden"
          }`}
          playsInline
          muted
          autoPlay
        />

        {/* Placeholder when Stream is inactive */}
        {!streamActive && !streamError && (
          <div className="absolute inset-0 bg-slate-950 flex flex-col items-center justify-center text-center p-6 gap-3 text-slate-400">
            <Video className="w-12 h-12 text-slate-600" />
            <div>
              <p className="text-sm font-semibold text-slate-300">Live Camera Standby</p>
              <p className="text-xs text-slate-500">
                Click 'Start Live Camera' to grant permission and activate stream.
              </p>
            </div>
            <button
              onClick={() => startCameraStream()}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-medium rounded-xl text-xs transition shadow-lg shadow-emerald-900/30"
            >
              Start Live Camera
            </button>
          </div>
        )}

        {/* 3 Vision Spatial Zones Overlay */}
        {streamActive && (
          <div className="absolute inset-0 pointer-events-none flex z-10">
            {/* Left Zone: 0% - 33% */}
            <div className="w-[33%] h-full border-r border-dashed border-sky-400/30 bg-sky-950/10 relative p-2">
              <div className="bg-sky-900/80 text-sky-200 border border-sky-500/40 text-[10px] font-mono px-2 py-0.5 rounded backdrop-blur inline-flex items-center gap-1">
                <span>LEFT ZONE</span>
                <span className="text-sky-400 font-semibold">(9:00 - 11:00)</span>
              </div>
            </div>

            {/* Center Zone: 34% - 66% */}
            <div className="w-[34%] h-full border-r border-dashed border-emerald-400/40 bg-emerald-950/10 relative p-2 flex justify-center">
              <div className="bg-emerald-900/80 text-emerald-200 border border-emerald-500/40 text-[10px] font-mono px-2 py-0.5 rounded backdrop-blur inline-flex items-center gap-1 h-fit">
                <span>CENTER ZONE</span>
                <span className="text-emerald-300 font-semibold">(12:00)</span>
              </div>
            </div>

            {/* Right Zone: 67% - 100% */}
            <div className="w-[33%] h-full bg-purple-950/10 relative p-2 flex justify-end">
              <div className="bg-purple-900/80 text-purple-200 border border-purple-500/40 text-[10px] font-mono px-2 py-0.5 rounded backdrop-blur inline-flex items-center gap-1 h-fit">
                <span>RIGHT ZONE</span>
                <span className="text-purple-300 font-semibold">(1:00 - 3:00)</span>
              </div>
            </div>
          </div>
        )}

        {/* Active Scan Animation Indicator */}
        {isAnalyzing && (
          <div className="absolute inset-0 bg-gradient-to-b from-transparent via-emerald-500/25 to-transparent h-20 w-full animate-pulse z-20 pointer-events-none" />
        )}
      </div>

      {/* Footer Info */}
      <div className="p-3 bg-slate-950 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400 flex-wrap gap-2">
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          Camera stream piped directly to Gemini 3.6 Flash AI
        </span>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 cursor-pointer">
            <span>Auto-Scan Rate:</span>
            <select
              value={scanIntervalSeconds}
              onChange={(e) => setScanIntervalSeconds(Number(e.target.value))}
              className="bg-slate-900 border border-slate-800 rounded px-2 py-0.5 text-slate-200 focus:outline-none"
            >
              <option value={3}>3s</option>
              <option value={5}>5s</option>
              <option value={8}>8s</option>
              <option value={10}>10s</option>
            </select>
          </label>
        </div>
      </div>
    </div>
  );
};


