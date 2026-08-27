/**
 * SmartCane Core Configuration
 */

export interface SystemConfig {
  // Step length calibration constant K
  // Formula: SL = K * (a_max - a_min)^(1/4)
  defaultK: number;
  minK: number;
  maxK: number;
  
  // Safety & Hazard Thresholds
  immediateHazardDistanceMeters: number; // e.g. < 0.6m -> Immediate STOP!
  warningHazardDistanceMeters: number;   // e.g. < 1.5m -> Warning Obstacle Ahead
  
  // Speech Cooldown & Throttling (ms)
  hazardSpeechThrottleMs: number;        // Prevent repeating same obstacle every frame (default 4000ms)
  ambientSpeechThrottleMs: number;       // Background briefing throttle (default 12000ms)
  
  // Vision spatial divisions
  leftZoneBoundaryPercent: number;       // 0% - 33%
  centerZoneBoundaryPercent: number;     // 34% - 66%
  rightZoneBoundaryPercent: number;      // 67% - 100%
  
  // Hardware mode
  defaultHardwareMode: 'DEVELOPMENT' | 'RASPBERRY_PI';
}

export const SMARTCANE_CONFIG: SystemConfig = {
  defaultK: 0.45,
  minK: 0.20,
  maxK: 0.80,
  immediateHazardDistanceMeters: 0.6,
  warningHazardDistanceMeters: 1.5,
  hazardSpeechThrottleMs: 3500,
  ambientSpeechThrottleMs: 12000,
  leftZoneBoundaryPercent: 33,
  centerZoneBoundaryPercent: 66,
  rightZoneBoundaryPercent: 100,
  defaultHardwareMode: 'DEVELOPMENT'
};
