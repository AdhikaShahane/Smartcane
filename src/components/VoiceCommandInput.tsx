import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  Mic,
  MicOff,
  Radio,
  Sparkles,
  Volume2,
  ShieldCheck,
  Activity,
  AlertCircle,
  Unlock,
} from "lucide-react";

interface VoiceCommandInputProps {
  onSendCommand: (command: string) => void;
  isProcessing: boolean;
  isSpeaking: boolean;
  onListeningStateChange?: (isListening: boolean) => void;
}

// Common non-command background noise fillers to filter
const NOISE_ARTIFACTS = new Set([
  "a", "uh", "um", "ah", "er", "oh", "hm", "hmm", "shh", "ss", "the", "m", "huh", "p"
]);

export const VoiceCommandInput: React.FC<VoiceCommandInputProps> = ({
  onSendCommand,
  isProcessing,
  isSpeaking,
  onListeningStateChange,
}) => {
  const [inputText, setInputText] = useState<string>("");
  const [isListening, setIsListening] = useState<boolean>(false);
  const [permissionBlocked, setPermissionBlocked] = useState<boolean>(false);
  const [confidenceScore, setConfidenceScore] = useState<number | null>(null);
  const [micSupported, setMicSupported] = useState<boolean>(true);
  const [activeMicLabel, setActiveMicLabel] = useState<string>("");

  const recognitionRef = useRef<any>(null);
  const shouldListenRef = useRef<boolean>(true);
  const isProcessingRef = useRef<boolean>(isProcessing);
  const isSpeakingRef = useRef<boolean>(isSpeaking);

  useEffect(() => {
    isProcessingRef.current = isProcessing;
  }, [isProcessing]);

  useEffect(() => {
    isSpeakingRef.current = isSpeaking;
  }, [isSpeaking]);

  // Safe restart function for always-active listening loop
  const startContinuousListening = useCallback(() => {
    if (!recognitionRef.current || isSpeakingRef.current) return;
    try {
      recognitionRef.current.start();
    } catch (err: any) {
      if (err.name !== "InvalidStateError") {
        // Recognition might already be running, which is fine
      }
    }
  }, []);

  // Initialize Continuous Speech Recognition Engine on Mount
  useEffect(() => {
    if (typeof window === "undefined") return;

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setMicSupported(false);
      return;
    }

    try {
      const recog = new SpeechRecognition();
      recog.continuous = true;
      recog.interimResults = true;
      recog.lang = "en-US";

      recog.onstart = () => {
        setIsListening(true);
        setPermissionBlocked(false);
        if (onListeningStateChange) onListeningStateChange(true);
      };

      recog.onresult = (event: any) => {
        const current = event.resultIndex;
        const resultObj = event.results[current][0];
        const transcript = resultObj.transcript || "";
        const confidence = typeof resultObj.confidence === "number" ? resultObj.confidence : 1.0;

        if (confidence > 0) {
          setConfidenceScore(Math.round(confidence * 100));
        }

        setInputText(transcript);

        if (event.results[current].isFinal) {
          const finalQuery = transcript.trim();
          const lowerQuery = finalQuery.toLowerCase().replace(/[^\w\s]/gi, "");

          // Check if it's just filler noise
          if (!finalQuery || NOISE_ARTIFACTS.has(lowerQuery)) {
            setInputText("");
            return;
          }

          // Valid speech command received
          setInputText("");
          onSendCommand(finalQuery);
        }
      };

      recog.onerror = (event: any) => {
        if (event.error === "not-allowed" || event.error === "service-not-allowed") {
          setIsListening(false);
          setPermissionBlocked(true);
          if (onListeningStateChange) onListeningStateChange(false);
        } else if (event.error === "no-speech") {
          // No speech detected, restart automatically to keep ear open
          if (shouldListenRef.current && !isSpeakingRef.current) {
            setTimeout(startContinuousListening, 300);
          }
        }
      };

      recog.onend = () => {
        setIsListening(false);
        if (onListeningStateChange) onListeningStateChange(false);

        // Always restart if we should be listening and not speaking
        if (shouldListenRef.current && !isSpeakingRef.current) {
          setTimeout(startContinuousListening, 400);
        }
      };

      recognitionRef.current = recog;
      setMicSupported(true);

      // Attempt automatic start
      startContinuousListening();

      // Check audio device labels
      if (navigator.mediaDevices?.enumerateDevices) {
        navigator.mediaDevices.enumerateDevices().then((devices) => {
          const mics = devices.filter((d) => d.kind === "audioinput");
          if (mics.length > 0 && mics[0].label) {
            setActiveMicLabel(mics[0].label);
          }
        });
      }
    } catch (err) {
      console.warn("Speech recognition initialization notice:", err);
      setMicSupported(false);
    }

    return () => {
      shouldListenRef.current = false;
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch (e) {}
      }
    };
  }, [onSendCommand, onListeningStateChange, startContinuousListening]);

  // Pause recognition when robot itself is speaking to prevent self-trigger feedback
  useEffect(() => {
    if (isSpeaking) {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch (e) {}
      }
    } else {
      if (shouldListenRef.current && !isProcessing) {
        setTimeout(startContinuousListening, 600);
      }
    }
  }, [isSpeaking, isProcessing, startContinuousListening]);

  const quickCommands = [
    "Where is the chair?",
    "Where should I walk?",
    "What is today's weather?",
    "Is anything blocking my path?",
    "Are you ready?",
    "What can you do?",
  ];

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-2xl flex flex-col gap-4">
      {/* Top Listening Status Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2.5">
          <div
            className={`w-8 h-8 rounded-xl flex items-center justify-center border transition ${
              isSpeaking
                ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                : isListening
                ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40 animate-pulse"
                : "bg-slate-800 text-slate-400 border-slate-700"
            }`}
          >
            {isSpeaking ? (
              <Volume2 className="w-4 h-4 text-amber-400 animate-bounce" />
            ) : isListening ? (
              <Mic className="w-4 h-4 text-emerald-400" />
            ) : (
              <MicOff className="w-4 h-4 text-slate-400" />
            )}
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              Continuous Speech Intake (Hands-Free Ear)
              <span
                className={`text-[10px] px-2 py-0.5 rounded-full font-mono uppercase font-bold ${
                  isSpeaking
                    ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                    : isListening
                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                    : permissionBlocked
                    ? "bg-rose-500/20 text-rose-300 border border-rose-500/40 animate-pulse"
                    : "bg-slate-800 text-slate-400"
                }`}
              >
                {isSpeaking
                  ? "ROBOT SPEAKING"
                  : isListening
                  ? "ACTIVE EAR: LISTENING"
                  : permissionBlocked
                  ? "MIC PERMISSION REQUIRED"
                  : "INITIALIZING"}
              </span>
            </h3>
            <p className="text-xs text-slate-400">
              {activeMicLabel ? `Input Hardware: ${activeMicLabel}` : "Speak naturally at any time — SmartCane is continuously listening"}
            </p>
          </div>
        </div>

        {/* Confidence & Audio Telemetry */}
        <div className="flex items-center gap-2">
          {confidenceScore !== null && (
            <div className="bg-slate-950 border border-slate-800 px-2.5 py-1 rounded-lg text-[11px] font-mono text-emerald-400">
              Speech Conf: {confidenceScore}%
            </div>
          )}

          {permissionBlocked && (
            <button
              onClick={() => {
                setPermissionBlocked(false);
                startContinuousListening();
              }}
              className="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-slate-950 font-bold rounded-lg text-xs transition flex items-center gap-1.5 shadow-lg shadow-amber-900/30"
            >
              <Unlock className="w-3.5 h-3.5" />
              <span>Authorize Microphone</span>
            </button>
          )}
        </div>
      </div>

      {/* Live Audio Waveform & Speech Transcript Box */}
      <div className="bg-slate-950 border border-slate-800/90 rounded-xl p-4 flex flex-col gap-2 min-h-[85px] justify-center relative overflow-hidden">
        {/* Subtle glowing audio wave background when listening */}
        {isListening && (
          <div className="absolute inset-0 bg-gradient-to-r from-emerald-500/5 via-sky-500/5 to-emerald-500/5 pointer-events-none animate-pulse" />
        )}

        <div className="flex items-center justify-between text-xs text-slate-400 font-mono">
          <span className="flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5 text-emerald-400" />
            <span>REAL-TIME VOICE INTAKE STREAM</span>
          </span>
          <span className="text-[10px] text-slate-400">
            {isProcessing ? "PROCESSING INTENT..." : isSpeaking ? "AUDIO OUTPUT PLAYING" : "READY FOR SPEECH"}
          </span>
        </div>

        <div className="text-sm font-medium text-slate-200">
          {inputText ? (
            <span className="text-emerald-300 font-semibold italic">"{inputText}"</span>
          ) : isListening ? (
            <span className="text-slate-400 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping inline-block" />
              Listening for voice questions ("Where is the chair?", "What is today's weather?")...
            </span>
          ) : (
            <span className="text-slate-400">Microphone stream standby. Click 'Authorize Microphone' if prompted.</span>
          )}
        </div>
      </div>

      {/* Quick Verbal Speech Trigger Simulator (For Testing without Microphone) */}
      <div className="flex flex-col gap-2">
        <span className="text-xs font-semibold text-slate-400 flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
          Test Verbal Phrases (Simulate Voice Input):
        </span>
        <div className="flex flex-wrap gap-2">
          {quickCommands.map((cmd) => (
            <button
              key={cmd}
              onClick={() => onSendCommand(cmd)}
              disabled={isProcessing}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 hover:border-slate-600 text-slate-200 border border-slate-700/80 rounded-xl text-xs font-medium transition active:scale-95 disabled:opacity-50"
            >
              "{cmd}"
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
