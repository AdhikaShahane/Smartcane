/**
 * SmartCane Core Types & Robotic State Models
 */

export type SpatialZone = 'LEFT' | 'CENTER' | 'RIGHT';

export type HazardPriority = 'IMMEDIATE_COLLISION' | 'PATH_BLOCKING' | 'RELEVANT_OBJECT' | 'ORDINARY_CONTEXT';

export type CommunicationTier = 'Tier 1' | 'Tier 2' | 'Tier 3';

export type UserIntentType =
  | 'FIND_OBJECT'
  | 'PATH_GUIDANCE'
  | 'HAZARD_CHECK'
  | 'WEATHER_QUERY'
  | 'CONVERSATION'
  | 'SYSTEM_STATUS'
  | 'CALIBRATION'
  | 'UNKNOWN';

export interface BoundingBox {
  x: number;      // percent 0-100
  y: number;      // percent 0-100
  width: number;  // percent 0-100
  height: number; // percent 0-100
}

export interface DetectedObject {
  id: string;
  label: string;
  confidence: number;
  bbox: [number, number, number, number]; // [xPercent, yPercent, widthPercent, heightPercent]
  distanceMeters: number;
  calculatedSteps: number;
  spatialZone: SpatialZone;
  clockDirection: string; // e.g. "12 o'clock", "10 o'clock", "2 o'clock"
  isHazard: boolean;
  priority: HazardPriority;
  actionableAdvice: string;
}

export interface MPU6050AccelerationReading {
  ax: number; // m/s^2 or g
  ay: number;
  az: number;
  magnitude: number;
  timestamp: number;
}

export interface StepIntervalData {
  aMax: number;          // Maximum acceleration in step interval (m/s^2)
  aMin: number;          // Minimum acceleration in step interval (m/s^2)
  aDiff: number;         // (a_max - a_min)
  fourthRootDiff: number;// (a_max - a_min)^(1/4)
  calibrationK: number;  // K constant
  stepLengthMeters: number; // SL = K * (a_max - a_min)^(1/4)
  timestamp: number;
  isPeakValid: boolean;
}

export interface SensorSnapshot {
  ultrasonicDistanceCm: number;
  ultrasonicValid: boolean;
  mpuAccel: MPU6050AccelerationReading;
  stepInterval: StepIntervalData;
  totalStepsCount: number;
  isImpactDetected: boolean;
  pitchDeg: number;
  rollDeg: number;
  compassHeading: string;
  compassDegrees: number;
  gpsCoords: { lat: number; lng: number };
  gpsAddress: string;
  hardwareMode: 'DEVELOPMENT' | 'RASPBERRY_PI';
  batteryPercent: number;
  isConnected: boolean;
}

export interface WeatherData {
  temperatureC: number;
  weatherDescription: string;
  locationName: string;
  windSpeedKmh: number;
  humidityPercent: number;
  isRaining: boolean;
  timestamp: string;
}

export interface NavigationInstruction {
  targetLabel?: string;
  direction: 'FORWARD' | 'SLIGHT_LEFT' | 'SLIGHT_RIGHT' | 'STOP' | 'TURN_AROUND';
  distanceMeters: number;
  stepsCount: number;
  spokenText: string;
  priority: HazardPriority;
  tier: CommunicationTier;
  shouldChime: boolean;
}

export interface SpeechLog {
  id: string;
  timestamp: string;
  source: 'USER_COMMAND' | 'PROACTIVE_HAZARD' | 'NAVIGATION_GUIDE' | 'WEATHER' | 'SYSTEM';
  text: string;
  tier: CommunicationTier;
  stepsCalculated?: number;
  targetObject?: string;
}

export interface RoboticBrainState {
  isListening: boolean;
  isSpeaking: boolean;
  isVisionActive: boolean;
  isAssistanceActive: boolean;
  currentIntent: UserIntentType | null;
  lastSpokenText: string;
  lastSpokenTime: number;
  lastHazardAnnounced: string | null;
  lastHazardTime: number;
  detectedObjects: DetectedObject[];
  sensorSnapshot: SensorSnapshot;
  recentSpeechLogs: SpeechLog[];
}
