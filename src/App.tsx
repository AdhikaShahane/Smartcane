import React, { useState } from "react";
import {
  CommunicationTier,
  EmergencyContact,
  SensorTelemetry,
  VoiceSettings,
  AlertLog,
} from "./types";
import { VisionCanvas } from "./components/VisionCanvas";
import { AudioSpeechBanner } from "./components/AudioSpeechBanner";
import { HardwareTelemetry } from "./components/HardwareTelemetry";
import { FallSOSModal } from "./components/FallSOSModal";
import { VoiceCommandInput } from "./components/VoiceCommandInput";
import { EmergencyContactManager } from "./components/EmergencyContactManager";
import { RulesReferenceDrawer } from "./components/RulesReferenceDrawer";
import { LiveVoiceConversation } from "./components/LiveVoiceConversation";
import { GroundedInformationPanel } from "./components/GroundedInformationPanel";
import { processOfflineEdgeAlert, calculateSteps } from "./utils/yoloEdgeDetector";
import { Eye, Radio, Volume2, AlertOctagon, Sparkles, MapPin, Globe } from "lucide-react";

export default function App() {
  // 1. Settings state
  const [voiceSettings, setVoiceSettings] = useState<VoiceSettings>({
    stepLengthMeters: 0.75,
    voicePitch: 0.85, // Low-pitched grounded male tone
    voiceRate: 0.95,
    enableHaptics: true,
    volume: 1.0,
    preferredVoiceName: "Male Grounded",
    onlineMode: true, // true = Gemini 2.5 Flash, false = Edge YOLO
  });

  // 2. Hardware telemetry state
  const [telemetry, setTelemetry] = useState<SensorTelemetry>({
    ultrasonicCm: 150,
    stepCount: 428,
    pitchDeg: 2,
    rollDeg: 1,
    isImpactDetected: false,
    isConnected: true,
    compassHeading: "Facing North (12 o'clock)",
    gpsCoords: { lat: 28.6139, lng: 77.2090 },
    address: "Connaught Place, Central Concourse & Cafe Lobby",
  });

  // 3. Speech output & alerts
  const [currentSpeechText, setCurrentSpeechText] = useState<string>(
    "[CHIME] Sahayak Drishti active. Live camera stream connected."
  );
  const [tier, setTier] = useState<CommunicationTier>("Tier 2");
  const [source, setSource] = useState<string>("Gemini 2.5 Flash");
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);

  // 4. Fall & Emergency SOS state
  const [isFallModalOpen, setIsFallModalOpen] = useState<boolean>(false);
  const [emergencyContacts, setEmergencyContacts] = useState<EmergencyContact[]>([
    {
      id: "c-1",
      name: "Dr. Rajesh Shahane",
      relationship: "Family Primary",
      phone: "+1 (555) 019-2831",
      primary: true,
    },
    {
      id: "c-2",
      name: "Emergency Mobility Response",
      relationship: "Caregiver",
      phone: "+1 (555) 911-0022",
      primary: false,
    },
  ]);

  // 5. Alert Log History
  const [alertLogs, setAlertLogs] = useState<AlertLog[]>([
    {
      id: "log-1",
      timestamp: new Date().toLocaleTimeString(),
      text: "[CHIME] Sahayak Drishti initialized with live camera & voice guidance.",
      tier: "Tier 3",
      source: "Gemini 2.5 Flash",
      chime: true,
    },
  ]);

  const updateVoiceSettings = (updates: Partial<VoiceSettings>) => {
    setVoiceSettings((prev) => ({ ...prev, ...updates }));
  };

  const updateTelemetry = (updates: Partial<SensorTelemetry>) => {
    setTelemetry((prev) => {
      const next = { ...prev, ...updates };
      // Check for immediate ultrasonic hazard (< 50cm)
      if (next.ultrasonicCm > 0 && next.ultrasonicCm <= 50) {
        const steps = calculateSteps(next.ultrasonicCm / 100, voiceSettings.stepLengthMeters);
        triggerSpeechOutput(`Stop! Immediate obstacle ${steps} step ahead.`, "Tier 1", "Ultrasonic Hardware");
      }
      return next;
    });
  };

  const addAlertLog = (text: string, logTier: CommunicationTier, logSource: string) => {
    const newLog: AlertLog = {
      id: "log-" + Date.now(),
      timestamp: new Date().toLocaleTimeString(),
      text,
      tier: logTier,
      source: logSource as any,
      chime: text.includes("[CHIME]"),
    };
    setAlertLogs((prev) => [newLog, ...prev.slice(0, 19)]);
  };

  const triggerSpeechOutput = (text: string, outputTier: CommunicationTier, outputSource: string) => {
    if (!text) return;
    setCurrentSpeechText(text);
    setTier(outputTier);
    setSource(outputSource);
    addAlertLog(text, outputTier, outputSource);
  };

  // Process Vision Frame with Gemini Online or Edge Offline
  const handleAnalyzeFrame = async (customUserQuery?: string, imageBase64?: string) => {
    setIsAnalyzing(true);

    if (!voiceSettings.onlineMode) {
      // Offline Edge YOLO Fallback
      setTimeout(() => {
        const result = processOfflineEdgeAlert(
          [],
          telemetry.ultrasonicCm,
          voiceSettings.stepLengthMeters
        );
        triggerSpeechOutput(result.text, result.tier, "Edge YOLO Fallback");
        setIsAnalyzing(false);
      }, 400);
      return;
    }

    // Online Gemini 2.5 Flash API Route
    try {
      const response = await fetch("/api/analyze-vision", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          userQuery: customUserQuery || "Analyze path and obstacles ahead for safe walking",
          sensorData: telemetry,
          stepLength: voiceSettings.stepLengthMeters,
          environmentContext: "Live MediaDevices Camera Feed",
          imageBase64: imageBase64 || undefined,
        }),
      });

      const data = await response.json();
      if (data.response) {
        triggerSpeechOutput(data.response, data.tier || "Tier 2", data.source || "Gemini 2.5 Flash");
      } else {
        triggerSpeechOutput("Path is clear. Continue straight.", "Tier 2", "Gemini 2.5 Flash");
      }
    } catch (err) {
      console.error("Vision Analysis Error:", err);
      // Edge rule fallback on network drop
      const result = processOfflineEdgeAlert(
        [],
        telemetry.ultrasonicCm,
        voiceSettings.stepLengthMeters
      );
      triggerSpeechOutput(result.text, result.tier, "Edge YOLO Fallback");
    } finally {
      setIsAnalyzing(false);
    }
  };

  // Orientation Recovery Button Tap
  const handleOrientationRecovery = () => {
    const text = `You are facing North toward the main concourse road.`;
    triggerSpeechOutput(text, "Tier 2", "Orientation Tap");
  };

  // Ambient Briefing Button Tap
  const handleBriefingTap = () => {
    handleAnalyzeFrame("Give a comprehensive spatial safety briefing of what is in front of me.");
  };

  // Voice Query Submission
  const handleVoiceCommand = (query: string) => {
    if (
      query.toLowerCase().includes("cancel") ||
      query.toLowerCase().includes("okay") ||
      query.toLowerCase().includes("yes") ||
      query.toLowerCase().includes("stop sos")
    ) {
      setIsFallModalOpen(false);
      triggerSpeechOutput("SOS canceled. System resuming normal navigation.", "Tier 2", "Voice Command");
      return;
    }
    handleAnalyzeFrame(query);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans antialiased selection:bg-emerald-500 selection:text-slate-950 pb-16">
      {/* Top Main Navigation Header */}
      <header className="sticky top-0 z-40 bg-slate-950/90 backdrop-blur-md border-b border-slate-800 px-4 sm:px-8 py-3.5 flex items-center justify-between gap-4 shadow-xl">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-emerald-600 to-teal-400 flex items-center justify-center text-slate-950 font-black shadow-lg shadow-emerald-900/40">
            <Eye className="w-6 h-6 stroke-[2.5]" />
          </div>
          <div>
            <h1 className="text-base font-extrabold tracking-tight text-white flex items-center gap-2">
              SAHAYAK DRISHTI
              <span className="text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 px-2 py-0.5 rounded-full uppercase">
                Smart Cane Assistant
              </span>
            </h1>
            <p className="text-xs text-slate-400">AI Spatial Mobility, Vision & Safety Companion</p>
          </div>
        </div>

        {/* System Hardware Status Badges */}
        <div className="hidden sm:flex items-center gap-3 text-xs">
          <div className="bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-xl flex items-center gap-2">
            <Radio className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
            <span className="text-slate-300">
              Mode: <strong className="text-emerald-300">{voiceSettings.onlineMode ? "Gemini 2.5 Flash" : "YOLO Edge"}</strong>
            </span>
          </div>

          <div className="bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-xl flex items-center gap-2 font-mono">
            <span className="text-slate-400">Step Length:</span>
            <strong className="text-sky-300">{(voiceSettings.stepLengthMeters * 100).toFixed(0)}cm</strong>
          </div>

          <button
            onClick={() => setIsFallModalOpen(true)}
            className="px-3.5 py-1.5 bg-red-600/20 hover:bg-red-600/30 text-red-300 border border-red-500/40 rounded-xl font-medium transition flex items-center gap-1.5 active:scale-95 shadow"
          >
            <AlertOctagon className="w-4 h-4 text-red-400" />
            <span>Test SOS</span>
          </button>
        </div>
      </header>

      {/* Main Container Layout */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 flex flex-col gap-6">
        {/* Section 1: Vision Camera Feed & Audio Persona Output */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column: Spatial Vision Canvas (7 Cols) */}
          <div className="lg:col-span-7 flex flex-col gap-4">
            <VisionCanvas
              voiceSettings={voiceSettings}
              onAnalyzeFrame={handleAnalyzeFrame}
              isAnalyzing={isAnalyzing}
            />
          </div>

          {/* Right Column: Audio Speech Banner & Persona Controls (5 Cols) */}
          <div className="lg:col-span-5 flex flex-col gap-4">
            <AudioSpeechBanner
              currentSpeechText={currentSpeechText}
              tier={tier}
              source={source}
              voiceSettings={voiceSettings}
              onUpdateSettings={updateVoiceSettings}
            />

            {/* Live Voice Query Push to Talk Input */}
            <VoiceCommandInput
              onSendCommand={handleVoiceCommand}
              isProcessing={isAnalyzing}
            />
          </div>
        </div>

        {/* Section 1.5: Real-time Live API Voice & Google Search / Maps Grounding */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <LiveVoiceConversation />
          <GroundedInformationPanel
            onSpeakText={(text) => triggerSpeechOutput(text, "Tier 3", "Grounded AI Information")}
          />
        </div>

        {/* Section 2: Arduino Hardware Telemetry & Sensor Controls */}
        <HardwareTelemetry
          telemetry={telemetry}
          onUpdateTelemetry={updateTelemetry}
          voiceSettings={voiceSettings}
          onUpdateVoiceSettings={updateVoiceSettings}
          onTriggerFallProtocol={() => setIsFallModalOpen(true)}
          onTriggerOrientationRecovery={handleOrientationRecovery}
          onTriggerBriefing={handleBriefingTap}
        />

        {/* Section 3: Emergency Contacts & System Rules Reference */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <EmergencyContactManager
            contacts={emergencyContacts}
            onUpdateContacts={setEmergencyContacts}
          />

          {/* Alert History Feed Log */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl flex flex-col gap-3">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <h3 className="text-xs font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                <Volume2 className="w-3.5 h-3.5 text-emerald-400" /> Sahayak Speech Alert Log
              </h3>
              <span className="text-[10px] text-slate-400 font-mono">Recent 20 Messages</span>
            </div>

            <div className="flex flex-col gap-2 max-h-56 overflow-y-auto pr-1 scrollbar-thin">
              {alertLogs.map((log) => (
                <div
                  key={log.id}
                  className="bg-slate-950 p-2.5 rounded-xl border border-slate-800/80 flex items-start justify-between gap-2 text-xs"
                >
                  <div className="flex flex-col gap-0.5">
                    <div className="flex items-center gap-2 text-[10px]">
                      <span
                        className={`font-mono font-bold px-1.5 py-0.2 rounded ${
                          log.tier === "Tier 1"
                            ? "bg-red-500/20 text-red-300"
                            : log.tier === "Tier 2"
                            ? "bg-emerald-500/20 text-emerald-300"
                            : "bg-indigo-500/20 text-indigo-300"
                        }`}
                      >
                        {log.tier}
                      </span>
                      <span className="text-slate-500 font-mono">{log.timestamp}</span>
                      <span className="text-slate-400">• {log.source}</span>
                    </div>
                    <p className="text-slate-200 font-medium">{log.text}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Section 4: Rules Reference Sheet */}
        <RulesReferenceDrawer />
      </main>

      {/* Fall Protocol Emergency SOS Modal */}
      <FallSOSModal
        isOpen={isFallModalOpen}
        onCancel={() => setIsFallModalOpen(false)}
        telemetry={telemetry}
        emergencyContacts={emergencyContacts}
      />
    </div>
  );
}
