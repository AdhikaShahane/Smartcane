/**
 * HC-SR04 Ultrasonic Distance Sensor Module
 * 
 * Provides proximity sensing and physical close-range obstacle confirmation.
 */

import { SMARTCANE_CONFIG } from "../core/config";

export class UltrasonicSensor {
  private currentDistanceCm: number = 200;
  private lastValidReadingTime: number = Date.now();

  /**
   * Update reading from HC-SR04 (echo pulse calculation: distance = duration * 0.034 / 2)
   */
  public updateDistance(distanceCm: number): void {
    if (isNaN(distanceCm) || distanceCm < 2 || distanceCm > 450) {
      // Out of sensor range (2cm to 450cm)
      return;
    }
    this.currentDistanceCm = distanceCm;
    this.lastValidReadingTime = Date.now();
  }

  public getDistanceCm(): number {
    return this.currentDistanceCm;
  }

  public getDistanceMeters(): number {
    return parseFloat((this.currentDistanceCm / 100).toFixed(2));
  }

  /**
   * Check if an immediate close-range collision risk is detected
   */
  public isImmediateCollisionRisk(): boolean {
    const distanceM = this.getDistanceMeters();
    return distanceM <= SMARTCANE_CONFIG.immediateHazardDistanceMeters;
  }

  /**
   * Check if warning threshold is reached
   */
  public isWarningProximity(): boolean {
    const distanceM = this.getDistanceMeters();
    return distanceM <= SMARTCANE_CONFIG.warningHazardDistanceMeters;
  }
}

export const ultrasonicSensor = new UltrasonicSensor();
