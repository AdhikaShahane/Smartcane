import React from "react";
import { Mic, Cpu, Eye, Footprints, Volume2, ArrowRight, ShieldAlert, CloudSun } from "lucide-react";
import { UserIntentType, StepIntervalData, CommunicationTier } from "../core/types";

interface RoboticBrainPipelineProps {
  currentIntent: UserIntentType | null;
  lastUserQuery: string;
  lastSpokenText: string;
  currentTier: CommunicationTier;
  stepInterval: StepIntervalData;
  isListening: boolean;
  isSpeaking: boolean;
}

export const RoboticBrainPipeline: React.FC<RoboticBrainPipelineProps> = ({
  currentIntent,
  lastUserQuery,
  lastSpokenText,
  currentTier,
  stepInterval,
  isListening,
  isSpeaking
}) => {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 text-white shadow-xl flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-sky-500/10 border border-sky-500/30 text-sky-400">
            <Cpu className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              SmartCane Autonomous AI Brain Pipeline
              <span className="px-2 py-0.5 text-[10px] font-mono rounded-full bg-sky-500/20 text-sky-300 border border-sky-500/40">
                ORCHESTRATOR v2
              </span>
            </h3>
            <p className="text-xs text-slate-400">
              Perception → Reasoning → MPU6050 Gait SL → Actionable Natural Speech
            </p>
          </div>
        </div>
      </div>

      {/* 5-Stage Visual Workflow Diagram */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-2.5">
        {/* Stage 1: Ear / Mic */}
        <div className={`p-3 rounded-xl border transition-all ${
          isListening ? "bg-emerald-950/40 border-emerald-500/50 shadow-lg shadow-emerald-950/40" : "bg-slate-950/80 border-slate-800"
        }`}>
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span className="text-slate-400 font-mono text-[10px] uppercase">1. Ears (Mic)</span>
            <Mic className={`w-3.5 h-3.5 ${isListening ? "text-emerald-400 animate-pulse" : "text-slate-500"}`} />
          </div>
          <div className="text-xs font-semibold text-slate-200 truncate">
            {lastUserQuery ? `"${lastUserQuery}"` : "Waiting for speech..."}
          </div>
          <span className="text-[10px] text-slate-500 block mt-1">Natural Speech Intake</span>
        </div>

        {/* Stage 2: Intent Understanding */}
        <div className="p-3 rounded-xl border bg-slate-950/80 border-slate-800">
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span className="text-slate-400 font-mono text-[10px] uppercase">2. Intent</span>
            <Cpu className="w-3.5 h-3.5 text-sky-400" />
          </div>
          <div className="text-xs font-bold font-mono text-sky-400 truncate">
            {currentIntent || "HAZARD_MONITOR"}
          </div>
          <span className="text-[10px] text-slate-500 block mt-1">Command Classifier</span>
        </div>

        {/* Stage 3: Eyes & Range (Camera / Ultrasonic) */}
        <div className="p-3 rounded-xl border bg-slate-950/80 border-slate-800">
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span className="text-slate-400 font-mono text-[10px] uppercase">3. Eyes & Range</span>
            <Eye className="w-3.5 h-3.5 text-amber-400" />
          </div>
          <div className="text-xs font-semibold text-slate-200">
            Spatial 3D Zones
          </div>
          <span className="text-[10px] text-amber-400/80 block mt-1">LEFT | CENTER | RIGHT</span>
        </div>

        {/* Stage 4: MPU6050 Gait & Steps */}
        <div className="p-3 rounded-xl border bg-slate-950/80 border-slate-800">
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span className="text-slate-400 font-mono text-[10px] uppercase">4. Gait Engine</span>
            <Footprints className="w-3.5 h-3.5 text-purple-400" />
          </div>
          <div className="text-xs font-bold font-mono text-purple-300">
            SL: {stepInterval.stepLengthMeters.toFixed(2)}m
          </div>
          <span className="text-[10px] text-slate-500 block mt-1">Formula: D / SL</span>
        </div>

        {/* Stage 5: Voice Output */}
        <div className={`p-3 rounded-xl border transition-all ${
          isSpeaking ? "bg-amber-950/40 border-amber-500/60" : "bg-slate-950/80 border-slate-800"
        }`}>
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span className="text-slate-400 font-mono text-[10px] uppercase">5. Voice Output</span>
            <Volume2 className={`w-3.5 h-3.5 ${isSpeaking ? "text-amber-400 animate-bounce" : "text-slate-500"}`} />
          </div>
          <div className="text-xs font-semibold text-amber-300 truncate">
            {currentTier} Active
          </div>
          <span className="text-[10px] text-slate-500 block mt-1">Natural Action Guidance</span>
        </div>
      </div>

      {/* Latest Brain Spoken Output Box */}
      <div className="bg-slate-950/90 rounded-xl p-3.5 border border-slate-800 flex items-start gap-3">
        <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 mt-0.5">
          <Volume2 className="w-4 h-4" />
        </div>
        <div className="flex-1">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[11px] font-mono text-slate-400 uppercase tracking-wider">
              Current Robot Spoken Output
            </span>
            <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full ${
              currentTier === "Tier 1" ? "bg-red-500/20 text-red-300 border border-red-500/40" :
              currentTier === "Tier 2" ? "bg-sky-500/20 text-sky-300 border border-sky-500/40" :
              "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
            }`}>
              {currentTier}
            </span>
          </div>
          <p className="text-sm font-medium text-slate-100 leading-relaxed">
            {lastSpokenText || "Listening for speech command..."}
          </p>
        </div>
      </div>
    </div>
  );
};
