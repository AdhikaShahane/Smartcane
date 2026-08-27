export type CommunicationTier = 'Tier 1' | 'Tier 2' | 'Tier 3';

export interface DetectedObject {
  id: string;
  label: string;
  classId: number;
  confidence: number;
  bbox: [number, number, number, number]; // [xPercent, yPercent, widthPercent, heightPercent]
  distanceMeters: number;
  steps: number;
  clockDirection: string; // e.g. "12 o'clock", "2 o'clock"
  zone: 'Left' | 'Center' | 'Right';
  actionableNote: string;
}

export interface SensorTelemetry {
  ultrasonicCm: number;
  stepCount: number;
  pitchDeg: number;
  rollDeg: number;
  isImpactDetected: boolean;
  isConnected: boolean;
  compassHeading: string;
  gpsCoords: { lat: number; lng: number };
  address: string;
}

export interface VoiceSettings {
  stepLengthMeters: number; // default 0.75m
  voicePitch: number; // default 0.85 (grounded male tone)
  voiceRate: number;  // default 0.95 (natural pacing)
  enableHaptics: boolean;
  volume: number;
  preferredVoiceName: string;
  onlineMode: boolean; // true = Gemini 2.5 Flash, false = Edge YOLO Fallback
}

export interface EmergencyContact {
  id: string;
  name: string;
  relationship: string;
  phone: string;
  primary: boolean;
}

export interface PresetScene {
  id: string;
  title: string;
  category: 'Indoor' | 'Outdoor' | 'Transit';
  description: string;
  imagePlaceholderUrl: string;
  detectedObjects: DetectedObject[];
  ambientBriefing: string;
}

export interface AlertLog {
  id: string;
  timestamp: string;
  text: string;
  tier: CommunicationTier;
  source: 'Gemini 2.5 Flash' | 'Edge YOLO Fallback' | 'Hardware Protocol';
  chime: boolean;
}
