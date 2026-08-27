/**
 * MPU6050 Accelerometer & Gait Processing Module
 * 
 * Handles real-time acceleration stream, gait peak/valley detection,
 * and extracts a_max and a_min for the step-length formula.
 */

import { MPU6050AccelerationReading, StepIntervalData } from "../core/types";
import { stepCalculator } from "../navigation/step_length_calculator";

export class MPU6050Processor {
  private buffer: { magnitude: number; timestamp: number }[] = [];
  private readonly bufferSize = 40; // ~1-2 seconds window at 20-30Hz
  private lastStepTime = 0;
  private minStepIntervalMs = 350; // Minimum time between consecutive footsteps (~2.8 steps/sec max)
  private currentStepCount = 0;
  private currentStepInterval: StepIntervalData;

  // Running acceleration metrics
  private currentReading: MPU6050AccelerationReading = {
    ax: 0,
    ay: 0,
    az: 9.81,
    magnitude: 9.81,
    timestamp: Date.now()
  };

  constructor() {
    // Initialize default resting step interval
    this.currentStepInterval = stepCalculator.calculateStepLength(10.8, 8.8);
  }

  /**
   * Process raw acceleration sample from MPU6050 (ax, ay, az in m/s^2 or g)
   */
  public pushSample(ax: number, ay: number, az: number): {
    isStepDetected: boolean;
    stepInterval: StepIntervalData;
    stepCount: number;
    magnitude: number;
  } {
    const timestamp = Date.now();
    // Calculate Euclidean acceleration magnitude
    const magnitude = Math.sqrt(ax * ax + ay * ay + az * az);

    this.currentReading = {
      ax,
      ay,
      az,
      magnitude,
      timestamp
    };

    this.buffer.push({ magnitude, timestamp });
    if (this.buffer.length > this.bufferSize) {
      this.buffer.shift();
    }

    let isStepDetected = false;

    // Detect step if enough history exists and refractory period elapsed
    if (this.buffer.length >= 15 && timestamp - this.lastStepTime > this.minStepIntervalMs) {
      // Find maximum and minimum acceleration in the recent gait window (~1.0s)
      let aMax = -Infinity;
      let aMin = Infinity;

      for (const sample of this.buffer) {
        if (sample.magnitude > aMax) aMax = sample.magnitude;
        if (sample.magnitude < aMin) aMin = sample.magnitude;
      }

      const aDiff = aMax - aMin;

      // Threshold: Step detection threshold when cane impacts ground during walking cycle (diff > 1.8 m/s^2)
      if (aDiff >= 1.5 && aMax > 10.5 && aMin < 9.0) {
        isStepDetected = true;
        this.lastStepTime = timestamp;
        this.currentStepCount += 1;

        // Calculate dynamic personalized step length using exact formula:
        // SL = K * (a_max - a_min)^(1/4)
        this.currentStepInterval = stepCalculator.calculateStepLength(aMax, aMin);
      }
    }

    return {
      isStepDetected,
      stepInterval: this.currentStepInterval,
      stepCount: this.currentStepCount,
      magnitude
    };
  }

  public getCurrentReading(): MPU6050AccelerationReading {
    return this.currentReading;
  }

  public getLatestStepInterval(): StepIntervalData {
    return this.currentStepInterval;
  }

  public getTotalStepCount(): number {
    return this.currentStepCount;
  }

  public resetStepCount(): void {
    this.currentStepCount = 0;
  }

  /**
   * Generates realistic simulated walking gait data when in Development Mode
   */
  public generateSimulatedGaitSample(phase: number): { ax: number; ay: number; az: number } {
    // Realistic walking waveform: base gravity (9.8 m/s^2) + gait oscillation
    const baseG = 9.81;
    const verticalAccel = baseG + 2.8 * Math.sin(phase) + 1.2 * Math.sin(2 * phase);
    const forwardAccel = 1.4 * Math.cos(phase);
    const lateralAccel = 0.6 * Math.sin(phase * 0.5);

    return {
      ax: parseFloat(lateralAccel.toFixed(2)),
      ay: parseFloat(forwardAccel.toFixed(2)),
      az: parseFloat(verticalAccel.toFixed(2))
    };
  }
}

export const mpuProcessor = new MPU6050Processor();
