import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  CommunicationTier,
  EmergencyContact,
  SensorTelemetry,
  VoiceSettings,
  AlertLog,
} from "./types";
import { StepIntervalData, UserIntentType } from "./core/types";
import { stepCalculator } from "./navigation/step_length_calculator";
import { mpuProcessor } from "./sensors/mpu6050_processor";
import { smartCaneBrain } from "./core/smartcane_orchestrator";
import { startupDiagnostics, SystemDiagnosticsReport } from "./core/diagnostics";
import { StartupDiagnosticsPanel } from "./components/StartupDiagnosticsPanel";
import { VisionCanvas } from "./components/VisionCanvas";
import { AudioSpeechBanner } from "./components/AudioSpeechBanner";
import { HardwareTelemetry } from "./components/HardwareTelemetry";
import { FallSOSModal } from "./components/FallSOSModal";
import { VoiceCommandInput } from "./components/VoiceCommandInput";
import { EmergencyContactManager } from "./components/EmergencyContactManager";
import { RulesReferenceDrawer } from "./components/RulesReferenceDrawer";
import { LiveVoiceConversation } from "./components/LiveVoiceConversation";
import { GroundedInformationPanel } from "./components/GroundedInformationPanel";
import { StepLengthVisualizer } from "./components/StepLengthVisualizer";
import { RoboticBrainPipeline } from "./components/RoboticBrainPipeline";
import { RaspberryPiDeploymentModal } from "./components/RaspberryPiDeploymentModal";
import { Eye, Radio, Volume2, AlertOctagon, Sparkles, Cpu, Footprints } from "lucide-react";

export default function App() {
  // 1. Diagnostics & Mode State
  const [currentMode, setCurrentMode] = useState<"DEVELOPMENT" | "RASPBERRY_PI">("DEVELOPMENT");
  const [diagReport, setDiagReport] = useState<SystemDiagnosticsReport>(() => startupDiagnostics.getReport());
  const [isInitializingDiag, setIsInitializingDiag] = useState<boolean>(true);
  const [cameraStatus, setCameraStatus] = useState<string>("INITIALIZING");
  const hasSpokenReadyRef = useRef<boolean>(false);

  // 2. Settings state
  const [voiceSettings, setVoiceSettings] = useState<VoiceSettings>({
    stepLengthMeters: 0.65,
    voicePitch: 0.85, // Low-pitched grounded tone
    voiceRate: 0.95,
    enableHaptics: true,
    volume: 1.0,
    preferredVoiceName: "Male Grounded",
    onlineMode: true,
  });

  // 3. Hardware telemetry & MPU6050 Gait state
  const [stepInterval, setStepInterval] = useState<StepIntervalData>(() =>
    stepCalculator.calculateStepLength(11.2, 8.6)
  );

  const [currentIntent, setCurrentIntent] = useState<UserIntentType | null>(null);
  const [lastUserQuery, setLastUserQuery] = useState<string>("");
  const [isListeningSpeech, setIsListeningSpeech] = useState<boolean>(true);
  const [isSpeakingSpeech, setIsSpeakingSpeech] = useState<boolean>(false);
  const [isPiModalOpen, setIsPiModalOpen] = useState<boolean>(false);

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

  // 4. Speech output & alerts
  const [currentSpeechText, setCurrentSpeechText] = useState<string>(
    "[CHIME] SmartCane is initializing all robotic subsystems..."
  );
  const [tier, setTier] = useState<CommunicationTier>("Tier 3");
  const [source, setSource] = useState<string>("System Boot Diagnostics");
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);

  // Run full startup diagnostics
  const runDiagnostics = useCallback(async (mode: "DEVELOPMENT" | "RASPBERRY_PI" = currentMode) => {
    setIsInitializingDiag(true);
    const report = await startupDiagnostics.runFullDiagnostics(mode);
    setDiagReport(report);
    setIsInitializingDiag(false);

    if (!hasSpokenReadyRef.current) {
      hasSpokenReadyRef.current = true;
      setTimeout(() => {
        triggerSpeechOutput(
          "[CHIME] SmartCane is ready. Step length is calibrated at 0.65 meters. I am listening.",
          "Tier 3",
          "Startup Diagnostics"
        );
      }, 900);
    }
  }, [currentMode]);

  useEffect(() => {
    runDiagnostics(currentMode);
  }, [runDiagnostics, currentMode]);

  // Register orchestrator speech handler
  useEffect(() => {
    smartCaneBrain.registerSpeechHandler((text, spokenTier) => {
      triggerSpeechOutput(text, spokenTier, "SmartCane AI Brain");
    });
  }, []);

  // Periodic MPU6050 gait simulation in development mode
  useEffect(() => {
    let phase = 0;
    const interval = setInterval(() => {
      phase += 0.2;
      const sample = mpuProcessor.generateSimulatedGaitSample(phase);
      const res = mpuProcessor.pushSample(sample.ax, sample.ay, sample.az);
      if (res.stepInterval) {
        setStepInterval(res.stepInterval);
        setVoiceSettings((prev) => ({
          ...prev,
          stepLengthMeters: res.stepInterval.stepLengthMeters,
        }));
      }
    }, 450);

    return () => clearInterval(interval);
  }, []);

  // 5. Fall & Emergency SOS state
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

  // 6. Alert Log History
  const [alertLogs, setAlertLogs] = useState<AlertLog[]>([
    {
      id: "log-1",
      timestamp: new Date().toLocaleTimeString(),
      text: "[CHIME] SmartCane robotic assistant initialized with MPU6050 gait calculation.",
      tier: "Tier 3",
      source: "Startup Diagnostics",
      chime: true,
    },
  ]);

  const updateVoiceSettings = (updates: Partial<VoiceSettings>) => {
    setVoiceSettings((prev) => ({ ...prev, ...updates }));
  };

  const updateTelemetry = (updates: Partial<SensorTelemetry>) => {
    setTelemetry((prev) => {
      const next = { ...prev, ...updates };
      // Check for immediate ultrasonic hazard (< 60cm)
      if (next.ultrasonicCm > 0 && next.ultrasonicCm <= 60) {
        const steps = stepCalculator.convertDistanceToSteps(
          next.ultrasonicCm / 100,
          stepInterval.stepLengthMeters
        );
        triggerSpeechOutput(
          `Stop! Immediate obstacle ${steps} step ahead.`,
          "Tier 1",
          "Ultrasonic Sensor"
        );
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
    setIsSpeakingSpeech(true);
    setTimeout(() => setIsSpeakingSpeech(false), 3200);
  };

  // Process Vision Frame & Voice Command through Orchestrator
  const handleAnalyzeFrame = async (customUserQuery?: string, imageBase64?: string) => {
    setIsAnalyzing(true);
    const query = customUserQuery || "Autonomous environmental hazard and path scan";
    setLastUserQuery(query);

    const intent = smartCaneBrain.classifyIntent(query);
    setCurrentIntent(intent);

    try {
      const response = await fetch("/api/orchestrate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          imageBase64: imageBase64 || undefined,
          aMax: stepInterval.aMax,
          aMin: stepInterval.aMin,
          calibrationK: stepInterval.calibrationK,
          ultrasonicCm: telemetry.ultrasonicCm,
          location: telemetry.gpsCoords,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        if (data.spokenText) {
          // Avoid repetitive non-critical chatter during silent ambient scanning
          const isSilentScan = query.includes("Autonomous environmental");
          const isClear = data.spokenText.toLowerCase().includes("clear");
          if (!isSilentScan || !isClear) {
            triggerSpeechOutput(data.spokenText, data.tier || "Tier 2", "SmartCane AI Brain");
          }
          if (data.stepLengthMeters) {
            setStepInterval((prev) => ({
              ...prev,
              stepLengthMeters: data.stepLengthMeters,
            }));
          }
          return;
        }
      }

      // Fallback local orchestrator pipeline
      const instruction = await smartCaneBrain.handleUserSpeechCommand(query, telemetry.gpsCoords);
      triggerSpeechOutput(instruction.spokenText, instruction.tier, "SmartCane Local Brain");
    } catch (err) {
      console.error("Orchestrator Error:", err);
      const instruction = await smartCaneBrain.handleUserSpeechCommand(query, telemetry.gpsCoords);
      triggerSpeechOutput(instruction.spokenText, instruction.tier, "SmartCane Offline Brain");
    } finally {
      setIsAnalyzing(false);
    }
  };

  // Orientation Recovery Button Tap
  const handleOrientationRecovery = () => {
    const text = `You are facing North toward the main concourse.`;
    triggerSpeechOutput(text, "Tier 2", "Orientation Sensor");
  };

  // Ambient Briefing Button Tap
  const handleBriefingTap = () => {
    handleAnalyzeFrame("Give a comprehensive spatial safety briefing of what is in front of me.");
  };

  // Voice Query Submission
  const handleVoiceCommand = (query: string) => {
    setLastUserQuery(query);
    if (
      query.toLowerCase().includes("cancel") ||
      query.toLowerCase().includes("okay") ||
      query.toLowerCase().includes("yes") ||
      query.toLowerCase().includes("stop sos")
    ) {
      setIsFallModalOpen(false);
      triggerSpeechOutput("SOS canceled. Resuming normal navigation.", "Tier 2", "Voice Command");
      return;
    }
    handleAnalyzeFrame(query);
  };

  const handleKChange = (newK: number) => {
    const updated = stepCalculator.calculateStepLength(stepInterval.aMax, stepInterval.aMin);
    setStepInterval(updated);
    setVoiceSettings((prev) => ({
      ...prev,
      stepLengthMeters: updated.stepLengthMeters,
    }));
  };

  const handleAuthorizePermissions = async () => {
    try {
      if (navigator.mediaDevices?.getUserMedia) {
        await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
        runDiagnostics();
      }
    } catch (e) {
      console.warn("User authorization completed or cancelled:", e);
      runDiagnostics();
    }
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
              SMARTCANE ROBOTIC BRAIN
              <span className="text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 px-2 py-0.5 rounded-full uppercase">
                {currentMode === "DEVELOPMENT" ? "DEV SUITE" : "PI DEPLOYMENT"}
              </span>
            </h1>
            <p className="text-xs text-slate-400">Speech-Controlled, Vision & Sensor Assistive AI Assistant</p>
          </div>
        </div>

        {/* System Hardware & Deployment Badges */}
        <div className="flex items-center gap-3 text-xs">
          {/* Raspberry Pi Deployment Guide Button */}
          <button
            onClick={() => setIsPiModalOpen(true)}
            className="px-3 py-1.5 bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/40 rounded-xl font-medium transition flex items-center gap-1.5 active:scale-95 shadow"
          >
            <Cpu className="w-3.5 h-3.5 text-purple-400" />
            <span className="hidden sm:inline">Raspberry Pi Service</span>
            <span className="sm:hidden">Pi Code</span>
          </button>

          <div className="hidden md:flex bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-xl items-center gap-2 font-mono">
            <Footprints className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-slate-400">SL:</span>
            <strong className="text-amber-300">{stepInterval.stepLengthMeters.toFixed(2)}m</strong>
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
        {/* Section 0: Real Startup Diagnostics Subsystem Panel */}
        <StartupDiagnosticsPanel
          report={diagReport}
          currentMode={currentMode}
          onModeChange={(m) => setCurrentMode(m)}
          onRerunDiagnostics={() => runDiagnostics(currentMode)}
          onRequestPermissions={handleAuthorizePermissions}
          isInitializing={isInitializingDiag}
        />

        {/* Section 1: Autonomous Brain Pipeline Visualizer */}
        <RoboticBrainPipeline
          currentIntent={currentIntent}
          lastUserQuery={lastUserQuery}
          lastSpokenText={currentSpeechText}
          currentTier={tier}
          stepInterval={stepInterval}
          isListening={isListeningSpeech}
          isSpeaking={isSpeakingSpeech}
        />

        {/* Section 2: Step-Length MPU6050 Formula & Calibration Engine */}
        <StepLengthVisualizer
          currentStepInterval={stepInterval}
          onKChange={handleKChange}
        />

        {/* Section 3: Vision Camera Feed & Continuous Audio Speech Controls */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column: Spatial Vision Canvas (7 Cols) */}
          <div className="lg:col-span-7 flex flex-col gap-4">
            <VisionCanvas
              voiceSettings={voiceSettings}
              onAnalyzeFrame={handleAnalyzeFrame}
              isAnalyzing={isAnalyzing}
              onCameraStatusChange={(st) => setCameraStatus(st)}
            />
          </div>

          {/* Right Column: Audio Speech Banner & Always-Active Speech Ear (5 Cols) */}
          <div className="lg:col-span-5 flex flex-col gap-4">
            <AudioSpeechBanner
              currentSpeechText={currentSpeechText}
              tier={tier}
              source={source}
              voiceSettings={voiceSettings}
              onUpdateSettings={updateVoiceSettings}
            />

            {/* Continuous Speech Intake (Hands-Free Ear) */}
            <VoiceCommandInput
              onSendCommand={handleVoiceCommand}
              isProcessing={isAnalyzing}
              isSpeaking={isSpeakingSpeech}
              onListeningStateChange={(l) => setIsListeningSpeech(l)}
            />
          </div>
        </div>

        {/* Section 4: Real-time Live API Voice & Google Search / Maps Grounding */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <LiveVoiceConversation />
          <GroundedInformationPanel
            onSpeakText={(text) => triggerSpeechOutput(text, "Tier 3", "Grounded AI Information")}
          />
        </div>

        {/* Section 5: Sensor Bus & Telemetry Controls */}
        <HardwareTelemetry
          telemetry={telemetry}
          onUpdateTelemetry={updateTelemetry}
          voiceSettings={voiceSettings}
          onUpdateVoiceSettings={updateVoiceSettings}
          onTriggerFallProtocol={() => setIsFallModalOpen(true)}
          onTriggerOrientationRecovery={handleOrientationRecovery}
          onTriggerBriefing={handleBriefingTap}
        />

        {/* Section 6: Emergency Contacts & System Rules Reference */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <EmergencyContactManager
            contacts={emergencyContacts}
            onUpdateContacts={setEmergencyContacts}
          />

          {/* Alert History Feed Log */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl flex flex-col gap-3">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <h3 className="text-xs font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                <Volume2 className="w-3.5 h-3.5 text-emerald-400" /> SmartCane Speech Alert Log
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

        {/* Section 7: Rules Reference Sheet */}
        <RulesReferenceDrawer />
      </main>

      {/* Fall Protocol Emergency SOS Modal */}
      <FallSOSModal
        isOpen={isFallModalOpen}
        onCancel={() => setIsFallModalOpen(false)}
        telemetry={telemetry}
        emergencyContacts={emergencyContacts}
      />

      {/* Raspberry Pi Deployment Modal */}
      <RaspberryPiDeploymentModal
        isOpen={isPiModalOpen}
        onClose={() => setIsPiModalOpen(false)}
      />
    </div>
  );
}
