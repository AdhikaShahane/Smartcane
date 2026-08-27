/**
 * SmartCane Central AI Orchestrator & Robotic Brain
 * 
 * Coordinates:
 * - Speech Intake & Intent Classification
 * - Visual Perception & Spatial Object Tracking
 * - MPU6050 Acceleration & Step-Length Estimation (SL = K * ⁴√(a_max - a_min))
 * - Distance-to-Steps Conversion (Steps = D / SL)
 * - Proactive Hazard Detection with Priority Queue & Throttling
 * - Live Internet/Weather Lookup
 * - Spoken Response Generation & TTS
 */

import {
  UserIntentType,
  DetectedObject,
  SensorSnapshot,
  NavigationInstruction,
  CommunicationTier,
  HazardPriority,
  RoboticBrainState
} from "./types";
import { SMARTCANE_CONFIG } from "./config";
import { stepCalculator } from "../navigation/step_length_calculator";
import { spatialAnalyzer } from "../navigation/spatial_analyzer";
import { mpuProcessor } from "../sensors/mpu6050_processor";
import { ultrasonicSensor } from "../sensors/ultrasonic_sensor";
import { weatherService } from "../internet/weather_service";

export class SmartCaneOrchestrator {
  private lastSpokenText: string = "";
  private lastSpokenTime: number = 0;
  private lastHazardObject: string | null = null;
  private lastHazardTime: number = 0;
  private isAssistanceActive: boolean = true;
  private detectedObjects: DetectedObject[] = [];
  
  // Audio speech callback
  private onSpeakCallback?: (text: string, tier: CommunicationTier, chime?: boolean) => void;

  public registerSpeechHandler(callback: (text: string, tier: CommunicationTier, chime?: boolean) => void) {
    this.onSpeakCallback = callback;
  }

  /**
   * Intent Classification from natural speech
   */
  public classifyIntent(query: string): UserIntentType {
    const q = query.toLowerCase().trim();
    if (!q) return 'UNKNOWN';

    // Weather intent
    if (q.includes("weather") || q.includes("temperature") || q.includes("forecast") || q.includes("rain")) {
      return 'WEATHER_QUERY';
    }

    // Object search intent
    if (
      q.includes("where is") || 
      q.includes("find the") || 
      q.includes("guide me to") || 
      q.includes("locate") || 
      q.includes("where's the")
    ) {
      return 'FIND_OBJECT';
    }

    // Path / walking direction intent
    if (
      q.includes("where should i walk") || 
      q.includes("where is the path") || 
      q.includes("is path clear") || 
      q.includes("which way") || 
      q.includes("clear path") || 
      q.includes("how do i walk")
    ) {
      return 'PATH_GUIDANCE';
    }

    // Hazard / obstacle query intent
    if (
      q.includes("blocking") || 
      q.includes("hazard") || 
      q.includes("obstacle") || 
      q.includes("what is in front") || 
      q.includes("is there anything") || 
      q.includes("is there a person") || 
      q.includes("in front of me") ||
      q.includes("anything ahead")
    ) {
      return 'HAZARD_CHECK';
    }

    // System status / calibration intent
    if (q.includes("ready") || q.includes("status") || q.includes("sensor") || q.includes("battery") || q.includes("step length")) {
      return 'SYSTEM_STATUS';
    }

    // General conversation
    if (q.includes("hello") || q.includes("hi") || q.includes("what can you do") || q.includes("who are you") || q.includes("help")) {
      return 'CONVERSATION';
    }

    return 'HAZARD_CHECK';
  }

  /**
   * Update active detected objects from camera vision system
   */
  public updateVisionDetections(objects: DetectedObject[]): void {
    this.detectedObjects = objects;

    // Check proactive hazard monitoring if navigation assistance is active
    if (this.isAssistanceActive) {
      this.evaluateProactiveHazards();
    }
  }

  /**
   * Continuous Hazard Monitor with Intelligent Throttling
   */
  private evaluateProactiveHazards(): void {
    const now = Date.now();
    const ultrasonicDistM = ultrasonicSensor.getDistanceMeters();
    const isCloseUltrasonic = ultrasonicSensor.isImmediateCollisionRisk();

    // 1. Immediate Collision Risk (<0.6m from ultrasonic or vision)
    if (isCloseUltrasonic) {
      if (now - this.lastHazardTime > 2500 || this.lastHazardObject !== "immediate_ultrasonic") {
        this.lastHazardObject = "immediate_ultrasonic";
        this.lastHazardTime = now;
        this.speak("Stop. Obstacle ahead.", "Tier 1", false);
      }
      return;
    }

    // 2. Vision Hazards (sorted by distance)
    const sortedObjects = [...this.detectedObjects].sort((a, b) => a.distanceMeters - b.distanceMeters);
    const primaryHazard = sortedObjects.find((o) => o.isHazard && o.distanceMeters <= SMARTCANE_CONFIG.warningHazardDistanceMeters);

    if (primaryHazard) {
      const hazardKey = `${primaryHazard.label}_${primaryHazard.spatialZone}`;
      const timeSinceLast = now - this.lastHazardTime;

      // Announce only if new obstacle, or significantly closer, or throttle period elapsed
      if (hazardKey !== this.lastHazardObject || timeSinceLast > SMARTCANE_CONFIG.hazardSpeechThrottleMs) {
        this.lastHazardObject = hazardKey;
        this.lastHazardTime = now;

        const currentStepInterval = mpuProcessor.getLatestStepInterval();
        const steps = stepCalculator.convertDistanceToSteps(primaryHazard.distanceMeters, currentStepInterval.stepLengthMeters);

        let spokenAlert = "";
        let tier: CommunicationTier = "Tier 2";

        if (primaryHazard.priority === 'IMMEDIATE_COLLISION' || primaryHazard.distanceMeters <= 0.6) {
          spokenAlert = "Stop. Obstacle ahead.";
          tier = "Tier 1";
        } else if (primaryHazard.spatialZone === 'CENTER') {
          spokenAlert = `Warning. ${primaryHazard.label} ahead. Move to your left.`;
          tier = "Tier 1";
        } else if (primaryHazard.spatialZone === 'LEFT') {
          spokenAlert = `${primaryHazard.label} on your left.`;
        } else {
          spokenAlert = `${primaryHazard.label} on your right.`;
        }

        this.speak(spokenAlert, tier, false);
      }
    }
  }

  /**
   * Main Speech-to-Intent-to-Action Pipeline
   */
  public async handleUserSpeechCommand(
    query: string,
    currentLocation?: { lat: number; lng: number }
  ): Promise<NavigationInstruction> {
    const intent = this.classifyIntent(query);
    const latestStepInterval = mpuProcessor.getLatestStepInterval();
    const sl = latestStepInterval.stepLengthMeters;

    console.log(`[SmartCane Brain] Processing query: "${query}" | Classified Intent: ${intent} | StepLength: ${sl}m`);

    switch (intent) {
      case 'WEATHER_QUERY': {
        const weather = await weatherService.getLiveWeather(
          currentLocation?.lat || 28.6139,
          currentLocation?.lng || 77.2090
        );
        const spoken = weatherService.formatSpokenResponse(weather);
        this.speak(spoken, "Tier 3", true);
        return {
          direction: 'FORWARD',
          distanceMeters: 0,
          stepsCount: 0,
          spokenText: spoken,
          priority: 'ORDINARY_CONTEXT',
          tier: 'Tier 3',
          shouldChime: true
        };
      }

      case 'FIND_OBJECT': {
        const targetWord = this.extractTargetObject(query);
        const found = this.detectedObjects.find((o) => 
          o.label.toLowerCase().includes(targetWord.toLowerCase()) ||
          targetWord.toLowerCase().includes(o.label.toLowerCase())
        );

        if (!found) {
          // If not in direct view, provide honest safety feedback
          const text = `I don't see a ${targetWord} in front of you right now. Turn slightly to scan the area.`;
          this.speak(text, "Tier 2", false);
          return {
            targetLabel: targetWord,
            direction: 'FORWARD',
            distanceMeters: 0,
            stepsCount: 0,
            spokenText: text,
            priority: 'RELEVANT_OBJECT',
            tier: 'Tier 2',
            shouldChime: false
          };
        }

        // Calculate steps using formula: Steps = D / SL
        const steps = stepCalculator.convertDistanceToSteps(found.distanceMeters, sl);
        let spoken = "";

        if (found.spatialZone === 'CENTER') {
          spoken = `The ${found.label} is ahead. Take approximately ${steps} steps forward.`;
        } else if (found.spatialZone === 'LEFT') {
          spoken = `The ${found.label} is ahead on your left. Take approximately ${steps} steps forward and move slightly left.`;
        } else {
          spoken = `The ${found.label} is ahead on your right. Move slightly right.`;
        }

        this.speak(spoken, "Tier 2", false);
        return {
          targetLabel: found.label,
          direction: found.spatialZone === 'LEFT' ? 'SLIGHT_LEFT' : found.spatialZone === 'RIGHT' ? 'SLIGHT_RIGHT' : 'FORWARD',
          distanceMeters: found.distanceMeters,
          stepsCount: steps,
          spokenText: spoken,
          priority: 'RELEVANT_OBJECT',
          tier: 'Tier 2',
          shouldChime: false
        };
      }

      case 'PATH_GUIDANCE': {
        // Evaluate visible clear walking vector
        const centerObstacle = this.detectedObjects.find(
          (o) => o.spatialZone === 'CENTER' && o.distanceMeters <= SMARTCANE_CONFIG.warningHazardDistanceMeters
        );
        const leftObstacle = this.detectedObjects.find(
          (o) => o.spatialZone === 'LEFT' && o.distanceMeters <= SMARTCANE_CONFIG.warningHazardDistanceMeters
        );
        const rightObstacle = this.detectedObjects.find(
          (o) => o.spatialZone === 'RIGHT' && o.distanceMeters <= SMARTCANE_CONFIG.warningHazardDistanceMeters
        );

        let spoken = "";
        let direction: 'FORWARD' | 'SLIGHT_LEFT' | 'SLIGHT_RIGHT' | 'STOP' = 'FORWARD';

        if (!centerObstacle && ultrasonicSensor.getDistanceMeters() > SMARTCANE_CONFIG.warningHazardDistanceMeters) {
          spoken = "The path ahead is clear. Walk straight.";
          direction = 'FORWARD';
        } else if (centerObstacle && !leftObstacle) {
          spoken = `An obstacle is blocking the path. Move slightly to the left.`;
          direction = 'SLIGHT_LEFT';
        } else if (centerObstacle && !rightObstacle) {
          spoken = `The path is blocked. Move to the right.`;
          direction = 'SLIGHT_RIGHT';
        } else {
          spoken = "Stop. Obstacle ahead.";
          direction = 'STOP';
        }

        this.speak(spoken, direction === 'STOP' ? "Tier 1" : "Tier 2", false);
        return {
          direction,
          distanceMeters: centerObstacle ? centerObstacle.distanceMeters : 3.0,
          stepsCount: centerObstacle ? stepCalculator.convertDistanceToSteps(centerObstacle.distanceMeters, sl) : 5,
          spokenText: spoken,
          priority: centerObstacle ? 'PATH_BLOCKING' : 'ORDINARY_CONTEXT',
          tier: direction === 'STOP' ? 'Tier 1' : 'Tier 2',
          shouldChime: false
        };
      }

      case 'HAZARD_CHECK': {
        const closest = [...this.detectedObjects].sort((a, b) => a.distanceMeters - b.distanceMeters)[0];
        const ultrasonicM = ultrasonicSensor.getDistanceMeters();

        let spoken = "";
        let tier: CommunicationTier = "Tier 2";

        if (ultrasonicM <= SMARTCANE_CONFIG.immediateHazardDistanceMeters) {
          spoken = "Stop. Obstacle ahead.";
          tier = "Tier 1";
        } else if (closest && closest.distanceMeters <= SMARTCANE_CONFIG.warningHazardDistanceMeters) {
          const steps = stepCalculator.convertDistanceToSteps(closest.distanceMeters, sl);
          if (closest.spatialZone === 'CENTER') {
            spoken = `Warning. ${closest.label} ahead, approximately ${steps} steps away. Move to your left.`;
          } else {
            spoken = `${closest.label} on your ${closest.spatialZone.toLowerCase()}.`;
          }
        } else if (this.detectedObjects.length > 0) {
          const first = this.detectedObjects[0];
          spoken = `I see a ${first.label} on your ${first.spatialZone.toLowerCase()}. Path ahead is manageable.`;
        } else {
          spoken = "Path is clear. No hazards detected in front of you.";
        }

        this.speak(spoken, tier, false);
        return {
          direction: 'FORWARD',
          distanceMeters: closest ? closest.distanceMeters : 0,
          stepsCount: closest ? stepCalculator.convertDistanceToSteps(closest.distanceMeters, sl) : 0,
          spokenText: spoken,
          priority: 'PATH_BLOCKING',
          tier,
          shouldChime: false
        };
      }

      case 'SYSTEM_STATUS': {
        const k = stepCalculator.getCalibrationK();
        const totalSteps = mpuProcessor.getTotalStepCount();
        const spoken = `Yes. I'm ready. Step length is calibrated at ${sl} meters using K factor ${k}. Total steps recorded: ${totalSteps}.`;
        this.speak(spoken, "Tier 3", true);
        return {
          direction: 'FORWARD',
          distanceMeters: 0,
          stepsCount: 0,
          spokenText: spoken,
          priority: 'ORDINARY_CONTEXT',
          tier: 'Tier 3',
          shouldChime: true
        };
      }

      case 'CONVERSATION':
      default: {
        const spoken = "I can help identify objects, detect hazards, guide you using step-based instructions, and provide information such as weather.";
        this.speak(spoken, "Tier 3", true);
        return {
          direction: 'FORWARD',
          distanceMeters: 0,
          stepsCount: 0,
          spokenText: spoken,
          priority: 'ORDINARY_CONTEXT',
          tier: 'Tier 3',
          shouldChime: true
        };
      }
    }
  }

  /**
   * Extract target noun from phrase (e.g., "Where is the chair?" -> "chair")
   */
  private extractTargetObject(query: string): string {
    const q = query.toLowerCase()
      .replace(/[?.,!]/g, "")
      .replace("where is the", "")
      .replace("where is a", "")
      .replace("where is", "")
      .replace("find the", "")
      .replace("guide me to the", "")
      .replace("guide me to", "")
      .replace("locate the", "")
      .replace("where's the", "")
      .trim();

    return q || "chair";
  }

  /**
   * Unified Speech Dispatcher
   */
  public speak(text: string, tier: CommunicationTier = "Tier 2", chime: boolean = false): void {
    if (!text || text === "SILENCE") return;
    this.lastSpokenText = text;
    this.lastSpokenTime = Date.now();

    if (this.onSpeakCallback) {
      this.onSpeakCallback(text, tier, chime);
    }
  }

  public setAssistanceActive(active: boolean) {
    this.isAssistanceActive = active;
  }

  public getBrainState(): Partial<RoboticBrainState> {
    return {
      isAssistanceActive: this.isAssistanceActive,
      lastSpokenText: this.lastSpokenText,
      lastSpokenTime: this.lastSpokenTime,
      detectedObjects: this.detectedObjects
    };
  }
}

export const smartCaneBrain = new SmartCaneOrchestrator();
