import React, { useEffect, useState } from "react";
import { CommunicationTier, VoiceSettings } from "../types";
import { Volume2, VolumeX, Play, AlertTriangle, ShieldCheck, BellRing, Sparkles, Mic } from "lucide-react";
import { playChimeSound, playHazardAlarmSound, triggerHapticFeedback } from "../utils/audioSynth";

interface AudioSpeechBannerProps {
  currentSpeechText: string;
  tier: CommunicationTier;
  source: string;
  voiceSettings: VoiceSettings;
  onUpdateSettings: (settings: Partial<VoiceSettings>) => void;
}

export const AudioSpeechBanner: React.FC<AudioSpeechBannerProps> = ({
  currentSpeechText,
  tier,
  source,
  voiceSettings,
  onUpdateSettings,
}) => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [availableVoices, setAvailableVoices] = useState<SpeechSynthesisVoice[]>([]);

  // Load browser TTS voices
  useEffect(() => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      const updateVoices = () => {
        const voices = window.speechSynthesis.getVoices();
        setAvailableVoices(voices);
      };
      updateVoices();
      window.speechSynthesis.onvoiceschanged = updateVoices;
    }
  }, []);

  // Main speech synthesis trigger function
  const speakText = (textToSpeak: string) => {
    if (!textToSpeak || textToSpeak === "SILENCE") return;

    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;

    // Cancel ongoing speech
    window.speechSynthesis.cancel();

    // Check for [CHIME] tag
    const hasChime = textToSpeak.includes("[CHIME]");
    if (hasChime) {
      playChimeSound();
    } else if (tier === "Tier 1") {
      playHazardAlarmSound("short");
    }

    if (voiceSettings.enableHaptics) {
      triggerHapticFeedback(tier === "Tier 1" ? [200, 100, 200] : [80]);
    }

    // Clean text for speech engine
    const cleanSpeech = textToSpeak.replace(/\[CHIME\]/gi, "").trim();
    if (!cleanSpeech) return;

    const utterance = new SpeechSynthesisUtterance(cleanSpeech);
    utterance.volume = voiceSettings.volume;
    utterance.rate = voiceSettings.voiceRate;
    utterance.pitch = voiceSettings.voicePitch; // Low pitched male voice (~0.85)

    // Select low-pitched male voice if available
    const maleVoice = availableVoices.find(
      (v) =>
        v.name.toLowerCase().includes("male") ||
        v.name.toLowerCase().includes("david") ||
        v.name.toLowerCase().includes("george") ||
        v.name.toLowerCase().includes("daniel") ||
        v.name.toLowerCase().includes("guy")
    );
    if (maleVoice) {
      utterance.voice = maleVoice;
    }

    utterance.onstart = () => setIsPlaying(true);
    utterance.onend = () => setIsPlaying(false);
    utterance.onerror = () => setIsPlaying(false);

    // Instant speech output execution without delay
    window.speechSynthesis.speak(utterance);
  };

  // Speak whenever new speech text arrives
  useEffect(() => {
    if (currentSpeechText) {
      speakText(currentSpeechText);
    }
  }, [currentSpeechText]);

  // Tier Color Styling
  const getTierBadge = () => {
    switch (tier) {
      case "Tier 1":
        return {
          bg: "bg-red-500/20 text-red-300 border-red-500/50",
          icon: <AlertTriangle className="w-4 h-4 text-red-400 animate-bounce" />,
          label: "Tier 1: Immediate Hazard",
        };
      case "Tier 2":
        return {
          bg: "bg-emerald-500/20 text-emerald-300 border-emerald-500/50",
          icon: <ShieldCheck className="w-4 h-4 text-emerald-400" />,
          label: "Tier 2: Actionable Navigation",
        };
      case "Tier 3":
        return {
          bg: "bg-indigo-500/20 text-indigo-300 border-indigo-500/50",
          icon: <BellRing className="w-4 h-4 text-indigo-400" />,
          label: "Tier 3: Ambient Briefing",
        };
      default:
        return {
          bg: "bg-slate-500/20 text-slate-300 border-slate-500/50",
          icon: <Sparkles className="w-4 h-4" />,
          label: "Speech Guidance",
        };
    }
  };

  const badge = getTierBadge();

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl flex flex-col gap-3">
      {/* Top Banner Status */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <div className={`px-2.5 py-1 rounded-full text-xs font-semibold border flex items-center gap-1.5 ${badge.bg}`}>
            {badge.icon}
            <span>{badge.label}</span>
          </div>
          <span className="text-xs text-slate-400 font-mono">
            Source: <strong className="text-slate-200">{source}</strong>
          </span>
        </div>

        {/* Persona Indicator */}
        <div className="flex items-center gap-2 text-xs text-slate-300 bg-slate-950 px-3 py-1 rounded-full border border-slate-800">
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span>Sahayak Male Voice (Calm Grounded)</span>
        </div>
      </div>

      {/* Main Text Output Display */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 flex items-center justify-between gap-4">
        <div className="flex items-start gap-3 flex-1">
          <div className={`mt-1 p-2 rounded-lg ${isPlaying ? "bg-emerald-500/20 text-emerald-400 animate-pulse" : "bg-slate-800 text-slate-400"}`}>
            <Volume2 className="w-5 h-5" />
          </div>
          <div>
            <div className="text-xs font-mono text-slate-400 mb-0.5 uppercase tracking-wider flex items-center gap-1">
              <span>Speech Audio Buffer</span>
              {currentSpeechText.includes("[CHIME]") && (
                <span className="text-[10px] bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 px-1.5 py-0.2 rounded">
                  [CHIME] Active
                </span>
              )}
            </div>
            <p className="text-lg font-medium text-slate-100 leading-relaxed font-sans">
              "{currentSpeechText || "Path is clear. Proceed with certainty."}"
            </p>
          </div>
        </div>

        {/* Play Replay Control Button */}
        <button
          onClick={() => speakText(currentSpeechText)}
          className="p-3 bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white rounded-xl shadow-lg shadow-emerald-900/40 transition shrink-0 flex items-center gap-2 font-medium text-xs"
        >
          <Play className="w-4 h-4 fill-white" />
          <span>Replay</span>
        </button>
      </div>

      {/* Audio Controls Footer */}
      <div className="flex items-center justify-between text-xs text-slate-400 pt-1 flex-wrap gap-3">
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <span>Volume:</span>
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={voiceSettings.volume}
              onChange={(e) => onUpdateSettings({ volume: parseFloat(e.target.value) })}
              className="w-20 accent-emerald-500"
            />
          </label>

          <label className="flex items-center gap-2 cursor-pointer">
            <span>Pitch:</span>
            <input
              type="range"
              min="0.5"
              max="1.2"
              step="0.05"
              value={voiceSettings.voicePitch}
              onChange={(e) => onUpdateSettings({ voicePitch: parseFloat(e.target.value) })}
              className="w-20 accent-emerald-500"
            />
            <span className="font-mono text-[11px] text-slate-300">{voiceSettings.voicePitch.toFixed(2)}</span>
          </label>
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 cursor-pointer text-slate-300">
            <input
              type="checkbox"
              checked={voiceSettings.enableHaptics}
              onChange={(e) => onUpdateSettings({ enableHaptics: e.target.checked })}
              className="accent-emerald-500 rounded"
            />
            <span>Enable Haptic Vibrations</span>
          </label>
        </div>
      </div>
    </div>
  );
};
