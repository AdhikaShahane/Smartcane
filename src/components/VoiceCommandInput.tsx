import React, { useState, useEffect, useRef } from "react";
import { Mic, MicOff, Send, Radio, AlertCircle, Sparkles, Volume2, ShieldCheck, Filter } from "lucide-react";

interface VoiceCommandInputProps {
  onSendCommand: (command: string) => void;
  isProcessing: boolean;
}

// List of common non-command filler sounds and background noise artifacts to ignore
const NOISE_ARTIFACTS = new Set([
  "a", "uh", "um", "ah", "er", "oh", "hm", "hmm", "shh", "ss", "the", "m", "huh", "p"
]);

export const VoiceCommandInput: React.FC<VoiceCommandInputProps> = ({
  onSendCommand,
  isProcessing,
}) => {
  const [inputText, setInputText] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [autoVoiceIntake, setAutoVoiceIntake] = useState(false); // Default to false to avoid permission blocks on initial page load
  const [noiseCancellationActive, setNoiseCancellationActive] = useState(true);
  const [speechConfidence, setSpeechConfidence] = useState<number | null>(null);
  const [micSupported, setMicSupported] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lastFilteredReason, setLastFilteredReason] = useState<string | null>(null);
  
  const recognitionRef = useRef<any>(null);
  const autoIntakeRef = useRef<boolean>(autoVoiceIntake);
  const isProcessingRef = useRef<boolean>(isProcessing);
  const noiseCancellationRef = useRef<boolean>(noiseCancellationActive);

  // Keep refs in sync
  useEffect(() => {
    autoIntakeRef.current = autoVoiceIntake;
  }, [autoVoiceIntake]);

  useEffect(() => {
    isProcessingRef.current = isProcessing;
  }, [isProcessing]);

  useEffect(() => {
    noiseCancellationRef.current = noiseCancellationActive;
  }, [noiseCancellationActive]);

  // Helper to start recognition safely
  const safeStartRecognition = () => {
    if (!recognitionRef.current) return;
    try {
      recognitionRef.current.start();
    } catch (err: any) {
      if (err.name !== "InvalidStateError") {
        console.warn("Speech start error:", err);
      }
    }
  };

  useEffect(() => {
    if (typeof window !== "undefined") {
      const SpeechRecognition =
        (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

      if (SpeechRecognition) {
        try {
          const recog = new SpeechRecognition();
          recog.continuous = false;
          recog.interimResults = true;
          recog.lang = "en-US";

          recog.onstart = () => {
            setIsListening(true);
            setErrorMessage(null);
          };

          recog.onresult = (event: any) => {
            const current = event.resultIndex;
            const resultObj = event.results[current][0];
            const transcript = resultObj.transcript || "";
            const confidence = typeof resultObj.confidence === "number" ? resultObj.confidence : 1.0;

            if (confidence > 0) {
              setSpeechConfidence(Math.round(confidence * 100));
            }

            setInputText(transcript);

            if (event.results[current].isFinal) {
              const finalQuery = transcript.trim();
              const lowerQuery = finalQuery.toLowerCase().replace(/[^\w\s]/gi, "");

              // Noise cancellation checks
              if (noiseCancellationRef.current) {
                // Check 1: Low speech confidence (< 25% confidence)
                if (confidence > 0 && confidence < 0.25) {
                  setLastFilteredReason(`Filtered low-confidence ambient noise (${Math.round(confidence * 100)}% conf)`);
                  setInputText("");
                  return;
                }

                // Check 2: Pure filler noise artifact
                if (!finalQuery || NOISE_ARTIFACTS.has(lowerQuery)) {
                  setLastFilteredReason(`Filtered background filler noise: "${finalQuery}"`);
                  setInputText("");
                  return;
                }
              }

              // Valid clear command accepted
              setLastFilteredReason(null);
              setInputText("");
              if (finalQuery) {
                onSendCommand(finalQuery);
              }
            }
          };

          recog.onerror = (event: any) => {
            setIsListening(false);
            if (event.error === "not-allowed" || event.error === "service-not-allowed") {
              setErrorMessage("Microphone permission required. Please click the Mic button to grant access.");
              setAutoVoiceIntake(false);
            } else {
              // For temporary errors like 'no-speech' or 'network', auto-retry if auto intake is enabled
              if (autoIntakeRef.current && !isProcessingRef.current) {
                setTimeout(() => {
                  if (autoIntakeRef.current) {
                    safeStartRecognition();
                  }
                }, 800);
              }
            }
          };

          recog.onend = () => {
            setIsListening(false);
            // Auto restart if continuous hands-free intake is enabled
            if (autoIntakeRef.current && !isProcessingRef.current) {
              setTimeout(() => {
                if (autoIntakeRef.current) {
                  safeStartRecognition();
                }
              }, 400);
            }
          };

          recognitionRef.current = recog;
          setMicSupported(true);
        } catch (err) {
          console.error("Speech recognition init error:", err);
          setMicSupported(false);
        }
      } else {
        setMicSupported(false);
      }
    }

    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch (e) {}
      }
    };
  }, [onSendCommand]);

  // Restart listening after AI processing finishes if Auto-Intake is enabled
  useEffect(() => {
    if (!isProcessing && autoVoiceIntake && !isListening) {
      const timer = setTimeout(() => {
        safeStartRecognition();
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [isProcessing, autoVoiceIntake, isListening]);

  const toggleMic = () => {
    setErrorMessage(null);
    if (!recognitionRef.current) {
      setErrorMessage("Speech recognition isn't supported in this browser. Please type below.");
      return;
    }

    if (isListening) {
      setAutoVoiceIntake(false);
      try {
        recognitionRef.current.stop();
      } catch (e) {}
      setIsListening(false);
    } else {
      setAutoVoiceIntake(true);
      safeStartRecognition();
    }
  };

  const toggleAutoVoiceIntake = () => {
    const nextVal = !autoVoiceIntake;
    setAutoVoiceIntake(nextVal);
    if (nextVal) {
      safeStartRecognition();
    } else {
      try {
        recognitionRef.current?.stop();
      } catch (e) {}
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim()) return;
    onSendCommand(inputText.trim());
    setInputText("");
  };

  const quickCommands = [
    "Is path clear?",
    "Where is the door handle?",
    "Where is an empty seat?",
    "Are there steps ahead?",
    "Cancel SOS / I am okay",
  ];

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-xl flex flex-col gap-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-xs font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
          <Mic className="w-3.5 h-3.5 text-emerald-400" /> Sahayak Voice Microphone Query
        </h3>

        <div className="flex items-center gap-2">
          {/* Gemini AI Status Badge */}
          <span className="px-2 py-0.5 text-[10px] font-mono rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-bold flex items-center gap-1">
            <Sparkles className="w-3 h-3 text-emerald-400" />
            Gemini AI Connected
          </span>

          {/* Noise Cancellation Toggle */}
          <button
            onClick={() => setNoiseCancellationActive(!noiseCancellationActive)}
            className={`px-2 py-1 text-[10px] font-mono rounded-lg border transition flex items-center gap-1 ${
              noiseCancellationActive
                ? "bg-indigo-500/20 text-indigo-300 border-indigo-500/40"
                : "bg-slate-800 text-slate-400 border-slate-700 hover:text-slate-200"
            }`}
            title="Filter ambient background noise and low-confidence chatter"
          >
            <ShieldCheck className="w-3 h-3 text-indigo-400" />
            <span>{noiseCancellationActive ? "NOISE CANCEL ON" : "NOISE CANCEL OFF"}</span>
          </button>

          {/* Hands-free Auto-Intake Toggle Button */}
          <button
            onClick={toggleAutoVoiceIntake}
            className={`px-2.5 py-1 text-[11px] font-mono rounded-lg border transition flex items-center gap-1 ${
              autoVoiceIntake
                ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                : "bg-slate-800 text-slate-400 border-slate-700 hover:text-slate-200"
            }`}
            title="Automatically listen for voice input continuously"
          >
            <Radio className="w-3 h-3 animate-pulse text-emerald-400" />
            <span>{autoVoiceIntake ? "AUTO INTAKE ON" : "AUTO INTAKE OFF"}</span>
          </button>

          <span className="text-[10px] text-slate-400 font-mono flex items-center gap-1">
            <span
              className={`w-2 h-2 rounded-full ${
                isListening ? "bg-red-500 animate-ping" : "bg-emerald-400"
              }`}
            />
            {isListening ? "LISTENING..." : "STANDBY"}
          </span>
        </div>
      </div>

      {/* Noise Cancellation Info / Speech Confidence Indicator */}
      {noiseCancellationActive && (
        <div className="flex items-center justify-between text-[10px] font-mono text-slate-400 bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-800/80">
          <span className="flex items-center gap-1 text-indigo-300">
            <Filter className="w-3 h-3 text-indigo-400" />
            Background Noise & Filler Filter Active
          </span>
          {speechConfidence !== null && isListening && (
            <span className="text-emerald-400 font-bold">
              Signal Clarity: {speechConfidence}%
            </span>
          )}
        </div>
      )}

      {lastFilteredReason && (
        <div className="bg-amber-950/40 border border-amber-800/50 text-amber-300 text-[11px] px-2.5 py-1 rounded-lg flex items-center justify-between">
          <span>{lastFilteredReason}</span>
          <button
            onClick={() => setLastFilteredReason(null)}
            className="text-amber-400 hover:text-amber-200 text-xs font-bold"
          >
            ×
          </button>
        </div>
      )}

      {errorMessage && (
        <div className="bg-red-950/80 border border-red-800 text-red-200 text-xs p-2 rounded-xl flex items-center gap-1.5">
          <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex items-center gap-2">
        <button
          type="button"
          onClick={toggleMic}
          className={`p-3.5 rounded-xl transition shadow flex items-center justify-center shrink-0 active:scale-95 ${
            isListening
              ? "bg-red-600 text-white animate-pulse ring-4 ring-red-900/50"
              : "bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-900/40"
          }`}
          title={isListening ? "Stop listening" : "Tap to Speak Voice Command"}
        >
          {isListening ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
        </button>

        <input
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder={
            isListening
              ? "Listening for clear voice command..."
              : "Tap mic or type query (e.g. 'Is path clear?')..."
          }
          className="flex-1 bg-slate-950 border border-slate-800 text-slate-100 text-xs rounded-xl px-4 py-3 focus:outline-none focus:border-emerald-500 placeholder-slate-500 font-medium"
        />

        <button
          type="submit"
          disabled={isProcessing || !inputText.trim()}
          className="p-3.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl shadow transition shrink-0 active:scale-95"
        >
          <Send className="w-4 h-4" />
        </button>
      </form>

      {/* Quick Command Chips */}
      <div className="flex items-center gap-1.5 overflow-x-auto pt-1 scrollbar-thin">
        <span className="text-[10px] text-slate-400 shrink-0 font-mono">Quick Query:</span>
        {quickCommands.map((cmd) => (
          <button
            key={cmd}
            onClick={() => {
              setInputText(cmd);
              onSendCommand(cmd);
            }}
            className="px-2.5 py-1 bg-slate-950 hover:bg-slate-800 text-slate-300 border border-slate-800 rounded-lg text-[11px] font-medium transition shrink-0 hover:text-emerald-300 active:scale-95"
          >
            {cmd}
          </button>
        ))}
      </div>
    </div>
  );
};

