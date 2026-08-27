/**
 * Spatial Analyzer & Environmental Scene Geometry
 * 
 * Maps 2D camera frame bounding boxes to 3D spatial zones (LEFT, CENTER, RIGHT),
 * calculates clock directions, estimates distance D, and determines obstacle priorities.
 */

import { SpatialZone, HazardPriority, DetectedObject } from "../core/types";
import { SMARTCANE_CONFIG } from "../core/config";
import { stepCalculator } from "./step_length_calculator";

export class SpatialAnalyzer {
  /**
   * Determine spatial zone from horizontal center percentage (0% to 100%)
   */
  public getSpatialZone(centerXPercent: number): SpatialZone {
    if (centerXPercent <= SMARTCANE_CONFIG.leftZoneBoundaryPercent) {
      return 'LEFT';
    } else if (centerXPercent <= SMARTCANE_CONFIG.centerZoneBoundaryPercent) {
      return 'CENTER';
    } else {
      return 'RIGHT';
    }
  }

  /**
   * Determine clock direction for natural navigational orientation
   */
  public getClockDirection(centerXPercent: number): string {
    if (centerXPercent < 20) return "9 o'clock";
    if (centerXPercent < 35) return "10 o'clock";
    if (centerXPercent < 45) return "11 o'clock";
    if (centerXPercent <= 55) return "12 o'clock";
    if (centerXPercent <= 65) return "1 o'clock";
    if (centerXPercent <= 80) return "2 o'clock";
    return "3 o'clock";
  }

  /**
   * Monocular Distance Estimation:
   * Uses bounding box vertical height and ground contact y-coordinate.
   * Objects closer to the bottom edge of the frame are physically closer to the cane.
   */
  public estimateDistance(
    bbox: [number, number, number, number], // [x%, y%, w%, h%]
    label: string,
    ultrasonicDistanceCm?: number
  ): number {
    const [, yPercent, , heightPercent] = bbox;
    const bottomContactY = yPercent + heightPercent; // 0 (top of frame) to 100 (bottom of frame)

    // Base optical geometric estimation:
    // Perspective projection formula based on camera mount angle (~45-60 deg down from vertical)
    let estimatedMeters = 3.5;

    if (bottomContactY > 90) {
      estimatedMeters = 0.5 + (100 - bottomContactY) * 0.05; // 0.5m - 1.0m
    } else if (bottomContactY > 75) {
      estimatedMeters = 1.0 + (90 - bottomContactY) * 0.06; // 1.0m - 1.9m
    } else if (bottomContactY > 55) {
      estimatedMeters = 1.9 + (75 - bottomContactY) * 0.08; // 1.9m - 3.5m
    } else {
      estimatedMeters = 3.5 + (55 - bottomContactY) * 0.12; // > 3.5m
    }

    // Adjust for specific known physical object sizes
    const l = label.toLowerCase();
    if (l.includes("bottle") || l.includes("cup") || l.includes("phone")) {
      // Small objects close to ground
      estimatedMeters *= 0.7;
    } else if (l.includes("door") || l.includes("wall") || l.includes("bus")) {
      // Large structural boundaries
      estimatedMeters = Math.max(1.2, estimatedMeters);
    }

    // Sensor Fusion with HC-SR04 ultrasonic range if object is in center cone
    if (ultrasonicDistanceCm && ultrasonicDistanceCm > 0 && ultrasonicDistanceCm < 400) {
      const ultrasonicMeters = ultrasonicDistanceCm / 100;
      // If ultrasonic detects something close and center zone, fuse with 60% weight on hardware ultrasonic
      if (ultrasonicMeters <= 2.0) {
        estimatedMeters = (ultrasonicMeters * 0.65) + (estimatedMeters * 0.35);
      }
    }

    return parseFloat(Math.max(0.3, estimatedMeters).toFixed(2));
  }

  /**
   * Evaluate hazard priority for safety-first decision making
   */
  public evaluateHazardPriority(
    label: string,
    distanceMeters: number,
    spatialZone: SpatialZone
  ): { isHazard: boolean; priority: HazardPriority } {
    const l = label.toLowerCase();
    const isObstacleClass = 
      l.includes("obstacle") || 
      l.includes("chair") || 
      l.includes("table") || 
      l.includes("person") || 
      l.includes("stairs") || 
      l.includes("vehicle") || 
      l.includes("car") || 
      l.includes("bicycle") || 
      l.includes("motorcycle") || 
      l.includes("pole") || 
      l.includes("wall");

    if (distanceMeters <= SMARTCANE_CONFIG.immediateHazardDistanceMeters) {
      return { isHazard: true, priority: 'IMMEDIATE_COLLISION' };
    }

    if (isObstacleClass && spatialZone === 'CENTER' && distanceMeters <= SMARTCANE_CONFIG.warningHazardDistanceMeters) {
      return { isHazard: true, priority: 'PATH_BLOCKING' };
    }

    if (isObstacleClass && distanceMeters <= 2.5) {
      return { isHazard: false, priority: 'RELEVANT_OBJECT' };
    }

    return { isHazard: false, priority: 'ORDINARY_CONTEXT' };
  }

  /**
   * Process raw detected bounding box into full DetectedObject model
   */
  public processDetectedObject(
    id: string,
    label: string,
    confidence: number,
    bbox: [number, number, number, number],
    ultrasonicCm?: number,
    stepLengthMeters?: number
  ): DetectedObject {
    const [xPercent, , widthPercent] = bbox;
    const centerX = xPercent + widthPercent / 2;

    const spatialZone = this.getSpatialZone(centerX);
    const clockDirection = this.getClockDirection(centerX);
    const distanceMeters = this.estimateDistance(bbox, label, ultrasonicCm);
    const calculatedSteps = stepCalculator.convertDistanceToSteps(distanceMeters, stepLengthMeters);
    const { isHazard, priority } = this.evaluateHazardPriority(label, distanceMeters, spatialZone);

    // Generate actionable guidance note
    let actionableAdvice = "";
    if (priority === 'IMMEDIATE_COLLISION') {
      actionableAdvice = `Stop. ${label} directly ahead.`;
    } else if (priority === 'PATH_BLOCKING') {
      actionableAdvice = `${label} ahead. Take approximately ${calculatedSteps} steps forward or move ${spatialZone === 'LEFT' ? 'right' : 'left'}.`;
    } else if (spatialZone === 'LEFT') {
      actionableAdvice = `${label} on your left at ${clockDirection}.`;
    } else if (spatialZone === 'RIGHT') {
      actionableAdvice = `${label} on your right at ${clockDirection}.`;
    } else {
      actionableAdvice = `${label} ahead. Approximately ${calculatedSteps} steps forward.`;
    }

    return {
      id,
      label,
      confidence: parseFloat(confidence.toFixed(2)),
      bbox,
      distanceMeters,
      calculatedSteps,
      spatialZone,
      clockDirection,
      isHazard,
      priority,
      actionableAdvice
    };
  }
}

export const spatialAnalyzer = new SpatialAnalyzer();
