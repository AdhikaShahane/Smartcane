import React, { useState } from "react";
import { BookOpen, ChevronDown, ChevronUp, CheckCircle2, Shield, Eye, Mic, Clock, Footprints } from "lucide-react";

export const RulesReferenceDrawer: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  const rules = [
    {
      id: 1,
      title: "1. Voice Persona & No Anti-Filler",
      desc: "Calm, grounded male voice with quiet authority. Absolutely NO phrases like 'As an AI...', 'I think...', or 'I am detecting...'. Direct certainty ('Path clear', 'Counter is 4 steps ahead').",
      icon: <Mic className="w-4 h-4 text-emerald-400" />,
    },
    {
      id: 2,
      title: "2. [CHIME] Confirmation Tag",
      desc: "Outputs [CHIME] tag before any multi-sentence contextual response or briefing so user knows assistant is active without checking hardware.",
      icon: <BookOpen className="w-4 h-4 text-indigo-400" />,
    },
    {
      id: 3,
      title: "3. Zero-Clutter Silence Rule",
      desc: "If path ahead is clear and no environmental changes occur, REMAIN SILENT. Silence builds user trust and prevents audio hazard.",
      icon: <Shield className="w-4 h-4 text-amber-400" />,
    },
    {
      id: 4,
      title: "4. Spatial Vision Zoning & Clock Directions",
      desc: "Left Zone (0-33% x-axis = 9 to 11 o'clock), Center Zone (34-66% = 12 o'clock), Right Zone (67-100% = 1 to 3 o'clock).",
      icon: <Eye className="w-4 h-4 text-sky-400" />,
    },
    {
      id: 5,
      title: "5. Actionable Guidance (Human Meaning)",
      desc: "Convert raw YOLO/COCO classes into actionable guidance: Bad: 'Door detected.' -> Good: 'Door handle is on your right side.'",
      icon: <CheckCircle2 className="w-4 h-4 text-emerald-400" />,
    },
    {
      id: 6,
      title: "6. Step-Based Gait Conversion",
      desc: "Convert all metric distances into calibrated step counts: N = ceil(D / SL). NEVER say '1.5 meters'. Always say '4 steps ahead'.",
      icon: <Footprints className="w-4 h-4 text-purple-400" />,
    },
    {
      id: 7,
      title: "7. Fall Protocol & SOS Broadcast",
      desc: "MPU6050 fall tilt triggers buzzer alarm, speaks 'Impact detected. Are you okay? Say Yes or press button', and 10s countdown to SMS broadcast.",
      icon: <Shield className="w-4 h-4 text-red-400" />,
    },
    {
      id: 8,
      title: "8. Dual-Path Architecture",
      desc: "Online Mode (Gemini 2.5/3.6 Flash) for rich vision context; Offline Edge Mode (YOLOv8 + Arduino sensors) for zero-downtime deterministic alerts.",
      icon: <Clock className="w-4 h-4 text-indigo-400" />,
    },
    {
      id: 9,
      title: "9. Strict 8-12 Word Count Limit",
      desc: "Standard guidance responses limited to 8 to 12 words maximum (20 words max for ambient briefings) for instantaneous processing.",
      icon: <CheckCircle2 className="w-4 h-4 text-emerald-400" />,
    },
  ];

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl shadow-xl overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full p-4 bg-slate-950 hover:bg-slate-900 text-slate-200 transition flex items-center justify-between text-xs font-semibold"
      >
        <span className="flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-emerald-400" />
          Sahayak Drishti Production System Rules Reference (9 Guidelines)
        </span>
        {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
      </button>

      {isOpen && (
        <div className="p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 bg-slate-900/90 text-xs text-slate-300 border-t border-slate-800">
          {rules.map((rule) => (
            <div key={rule.id} className="bg-slate-950 p-3 rounded-xl border border-slate-800/80 flex flex-col gap-1.5">
              <div className="font-semibold text-slate-100 flex items-center gap-2">
                {rule.icon}
                <span>{rule.title}</span>
              </div>
              <p className="text-slate-400 text-[11px] leading-relaxed">{rule.desc}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
