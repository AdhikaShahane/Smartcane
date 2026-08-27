import React, { useEffect, useState } from "react";
import { EmergencyContact, SensorTelemetry } from "../types";
import { AlertOctagon, PhoneCall, ShieldAlert, CheckCircle2, Send, Radio } from "lucide-react";
import { playHazardAlarmSound, triggerHapticFeedback } from "../utils/audioSynth";

interface FallSOSModalProps {
  isOpen: boolean;
  onCancel: () => void;
  telemetry: SensorTelemetry;
  emergencyContacts: EmergencyContact[];
}

export const FallSOSModal: React.FC<FallSOSModalProps> = ({
  isOpen,
  onCancel,
  telemetry,
  emergencyContacts,
}) => {
  const [countdown, setCountdown] = useState(10);
  const [sosSent, setSosSent] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      setCountdown(10);
      setSosSent(false);
      return;
    }

    // Play alarm sound and trigger haptics
    playHazardAlarmSound("siren");
    triggerHapticFeedback([300, 100, 300, 100, 300]);

    // Speak prompt
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const promptUtterance = new SpeechSynthesisUtterance(
        "Impact detected. Are you okay? Say Yes or press button to cancel S O S."
      );
      promptUtterance.rate = 0.95;
      promptUtterance.pitch = 0.85;
      window.speechSynthesis.speak(promptUtterance);
    }

    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          setSosSent(true);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [isOpen]);

  if (!isOpen) return null;

  const mapLink = `https://maps.google.com/?q=${telemetry.gpsCoords.lat},${telemetry.gpsCoords.lng}`;
  const primaryContact = emergencyContacts.find((c) => c.primary) || emergencyContacts[0];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/90 backdrop-blur-md animate-fade-in select-none">
      <div className="bg-slate-900 border-2 border-red-500 text-white rounded-3xl p-6 sm:p-8 max-w-lg w-full shadow-2xl flex flex-col gap-6 relative overflow-hidden">
        {/* Top Warning Pulse Line */}
        <div className="absolute top-0 left-0 right-0 h-2 bg-gradient-to-r from-red-600 via-amber-500 to-red-600 animate-pulse" />

        <div className="flex items-center gap-4">
          <div className="p-3 rounded-2xl bg-red-500/20 text-red-400 border border-red-500/40 animate-bounce">
            <AlertOctagon className="w-8 h-8" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              IMPACT DETECTED!
              <span className="text-xs font-mono font-normal bg-red-500/20 text-red-300 border border-red-500/40 px-2 py-0.5 rounded-full">
                Fall Protocol
              </span>
            </h2>
            <p className="text-xs text-slate-300">Smart Cane MPU6050 Sudden Motion Threshold Triggered</p>
          </div>
        </div>

        {/* Central Speech Voice Alert & Countdown */}
        {!sosSent ? (
          <div className="bg-red-950/40 border border-red-800/60 rounded-2xl p-5 text-center flex flex-col items-center gap-3">
            <p className="text-lg font-medium text-red-100">
              "Impact detected. Are you okay? Say 'Yes' or press button to cancel SOS."
            </p>

            <div className="flex items-center justify-center gap-3 my-2">
              <div className="w-16 h-16 rounded-full bg-red-600 text-white font-mono text-3xl font-bold flex items-center justify-center border-4 border-red-400 animate-pulse shadow-lg shadow-red-900/50">
                {countdown}
              </div>
              <span className="text-xs text-red-300 max-w-[120px] text-left">
                seconds until emergency contact SMS broadcast
              </span>
            </div>
          </div>
        ) : (
          <div className="bg-emerald-950/40 border border-emerald-800/60 rounded-2xl p-5 text-center flex flex-col items-center gap-3">
            <CheckCircle2 className="w-10 h-10 text-emerald-400" />
            <div>
              <h3 className="text-base font-bold text-emerald-200">EMERGENCY SOS BROADCAST SENT</h3>
              <p className="text-xs text-slate-300 mt-1">
                Emergency contacts alerted via SMS with live GPS coordinates.
              </p>
            </div>
          </div>
        )}

        {/* SOS SMS Payload Preview */}
        <div className="bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs flex flex-col gap-1.5 font-mono">
          <div className="flex items-center justify-between text-slate-400 text-[11px]">
            <span className="flex items-center gap-1 text-slate-300">
              <Send className="w-3 h-3 text-red-400" /> Outgoing Emergency SMS Payload:
            </span>
            <span className="text-slate-500">To: {primaryContact ? primaryContact.name : "Emergency Contacts"}</span>
          </div>
          <p className="text-slate-300 bg-slate-900 p-2.5 rounded border border-slate-800 leading-relaxed text-[11px]">
            🚨 EMERGENCY ALERT: Sahayak Drishti Smart Cane fall impact detected for user.
            <br />
            Location: {telemetry.address}
            <br />
            GPS: {telemetry.gpsCoords.lat.toFixed(5)}, {telemetry.gpsCoords.lng.toFixed(5)}
            <br />
            Map: <a href={mapLink} target="_blank" rel="noreferrer" className="text-sky-400 underline">{mapLink}</a>
          </p>
        </div>

        {/* Bottom Actions */}
        <div className="flex items-center gap-3 pt-2">
          <button
            onClick={onCancel}
            className="flex-1 py-3.5 px-4 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-2xl shadow-lg shadow-emerald-900/40 transition active:scale-95 flex items-center justify-center gap-2 text-sm"
          >
            <CheckCircle2 className="w-5 h-5" />
            <span>I'M OKAY / CANCEL SOS</span>
          </button>
        </div>
      </div>
    </div>
  );
};
