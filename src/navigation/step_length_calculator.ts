/**
 * SmartCane Step-Length Calculator
 * 
 * CORE FORMULA REQUIRED:
 * SL = K × ⁴√(a_max − a_min)
 * Equivalent: SL = K × (a_max − a_min)^(1/4)
 * 
 * Where:
 * - SL = estimated stride/step length in meters
 * - K = user-calibrated constant (default ~0.45)
 * - a_max = maximum acceleration measured during the walking-step interval (m/s^2)
 * - a_min = minimum acceleration measured during the walking-step interval (m/s^2)
 * 
 * DISTANCE TO STEPS FORMULA:
 * Steps = Distance / SL
 */

import { StepIntervalData } from "../core/types";
import { SMARTCANE_CONFIG } from "../core/config";

export class StepLengthCalculator {
  private calibrationK: number;

  constructor(initialK: number = SMARTCANE_CONFIG.defaultK) {
    this.calibrationK = Math.max(SMARTCANE_CONFIG.minK, Math.min(SMARTCANE_CONFIG.maxK, initialK));
  }

  /**
   * Get the current calibration constant K
   */
  public getCalibrationK(): number {
    return this.calibrationK;
  }

  /**
   * Set and persist the calibration constant K
   */
  public setCalibrationK(newK: number): void {
    if (isNaN(newK) || newK <= 0) return;
    this.calibrationK = Math.max(SMARTCANE_CONFIG.minK, Math.min(SMARTCANE_CONFIG.maxK, newK));
  }

  /**
   * Core Mathematical Calculation:
   * SL = K * ⁴√(a_max - a_min)
   * 
   * @param aMax Maximum acceleration peak in the step cycle (m/s^2)
   * @param aMin Minimum acceleration valley in the step cycle (m/s^2)
   * @returns Detailed StepIntervalData with calculated step length in meters
   */
  public calculateStepLength(aMax: number, aMin: number): StepIntervalData {
    // Calculate peak-to-peak acceleration difference (a_max - a_min)
    // Guarantee non-negative difference
    const aDiff = Math.max(0.01, aMax - aMin);

    // Compute fourth root: ⁴√(a_max - a_min) = (a_max - a_min)^0.25
    const fourthRootDiff = Math.pow(aDiff, 0.25);

    // Compute personalized step length SL = K * (a_max - a_min)^0.25
    let stepLengthMeters = this.calibrationK * fourthRootDiff;

    // Sanity boundary guard: human step length ranges typically between 0.30m and 1.10m
    stepLengthMeters = Math.max(0.30, Math.min(1.10, stepLengthMeters));

    return {
      aMax,
      aMin,
      aDiff: parseFloat(aDiff.toFixed(3)),
      fourthRootDiff: parseFloat(fourthRootDiff.toFixed(3)),
      calibrationK: parseFloat(this.calibrationK.toFixed(3)),
      stepLengthMeters: parseFloat(stepLengthMeters.toFixed(3)),
      timestamp: Date.now(),
      isPeakValid: aDiff >= 0.2 // Meaningful gait motion
    };
  }

  /**
   * Distance-to-Steps Conversion:
   * Number of Steps = Distance / SL
   * 
   * @param distanceMeters Target distance in meters
   * @param stepLengthMeters User's calculated SL (or uses current default)
   * @returns Integer count of steps required for natural voice guidance
   */
  public convertDistanceToSteps(distanceMeters: number, stepLengthMeters?: number): number {
    if (distanceMeters <= 0) return 0;
    
    const sl = stepLengthMeters && stepLengthMeters > 0 ? stepLengthMeters : 0.65;
    const rawSteps = distanceMeters / sl;

    // Round naturally for spoken guidance
    const steps = Math.max(1, Math.round(rawSteps));
    return steps;
  }

  /**
   * Calibrate K based on a known walking distance test.
   * e.g., If user walks a measured 10-meter line in N steps, with average (a_max - a_min),
   * K = MeasuredAverageStepLength / FourthRoot(AvgDiff)
   * 
   * @param measuredDistanceMeters Total distance walked (e.g. 10m)
   * @param totalStepsCount Number of steps counted
   * @param avgADiff Average (a_max - a_min) measured during test
   */
  public calibrateFromTest(measuredDistanceMeters: number, totalStepsCount: number, avgADiff: number): number {
    if (totalStepsCount <= 0 || avgADiff <= 0) return this.calibrationK;
    
    const actualAverageStepLength = measuredDistanceMeters / totalStepsCount;
    const fourthRoot = Math.pow(avgADiff, 0.25);
    
    const calculatedK = actualAverageStepLength / fourthRoot;
    this.setCalibrationK(calculatedK);
    return this.calibrationK;
  }
}

// Export singleton instance
export const stepCalculator = new StepLengthCalculator(SMARTCANE_CONFIG.defaultK);
