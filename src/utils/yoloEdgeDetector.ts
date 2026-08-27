import { DetectedObject, CommunicationTier } from "../types";

// Standard COCO dataset classes dictionary matching system prompt specification
export const COCO_CLASSES: Record<number, string> = {
  0: 'person', 1: 'bicycle', 2: 'car', 3: 'motorcycle', 4: 'airplane', 5: 'bus',
  6: 'train', 7: 'truck', 8: 'boat', 9: 'traffic light', 10: 'fire hydrant',
  11: 'stop sign', 12: 'parking meter', 13: 'bench', 14: 'bird', 15: 'cat',
  16: 'dog', 17: 'horse', 18: 'sheep', 19: 'cow', 20: 'elephant', 21: 'bear',
  22: 'zebra', 23: 'giraffe', 24: 'backpack', 25: 'umbrella', 26: 'handbag',
  27: 'tie', 28: 'suitcase', 29: 'frisbee', 30: 'skis', 31: 'snowboard',
  32: 'sports ball', 33: 'kite', 34: 'baseball bat', 35: 'baseball glove',
  36: 'skateboard', 37: 'surfboard', 38: 'tennis racket', 39: 'bottle',
  40: 'wine glass', 41: 'cup', 42: 'fork', 43: 'knife', 44: 'spoon', 45: 'bowl',
  46: 'banana', 47: 'apple', 48: 'sandwich', 49: 'orange', 50: 'broccoli',
  51: 'carrot', 52: 'hot dog', 53: 'pizza', 54: 'donut', 55: 'cake',
  56: 'chair', 57: 'couch', 58: 'potted plant', 59: 'bed', 60: 'dining table',
  61: 'toilet', 62: 'tv', 63: 'laptop', 64: 'mouse', 65: 'remote', 66: 'keyboard',
  67: 'cell phone', 68: 'microwave', 69: 'oven', 70: 'toaster', 71: 'sink',
  72: 'refrigerator', 73: 'book', 74: 'clock', 75: 'vase', 76: 'scissors',
  77: 'teddy bear', 78: 'hair drier', 79: 'toothbrush'
};

/**
 * Calculates spatial zone and clock-face direction based on object bounding box center X
 * Left Zone: 0% – 33% -> 9 o'clock to 11 o'clock
 * Center Zone: 34% – 66% -> 12 o'clock
 * Right Zone: 67% – 100% -> 1pm to 3 o'clock
 */
export function calculateSpatialZoneAndClock(bbox: [number, number, number, number]): {
  zone: 'Left' | 'Center' | 'Right';
  clockDirection: string;
} {
  const [x, , w] = bbox;
  const centerX = x + w / 2;

  if (centerX < 33) {
    // Left Zone (0-33%)
    if (centerX < 11) return { zone: 'Left', clockDirection: "9 o'clock" };
    if (centerX < 22) return { zone: 'Left', clockDirection: "10 o'clock" };
    return { zone: 'Left', clockDirection: "11 o'clock" };
  } else if (centerX <= 66) {
    // Center Zone (34-66%)
    return { zone: 'Center', clockDirection: "12 o'clock" };
  } else {
    // Right Zone (67-100%)
    if (centerX < 78) return { zone: 'Right', clockDirection: "1 o'clock" };
    if (centerX < 89) return { zone: 'Right', clockDirection: "2 o'clock" };
    return { zone: 'Right', clockDirection: "3 o'clock" };
  }
}

/**
 * Converts distance in meters to user step count using Gait Formula:
 * N = ceil( D / StepLength )
 */
export function calculateSteps(distanceMeters: number, stepLengthMeters: number = 0.75): number {
  if (distanceMeters <= 0) return 0;
  return Math.ceil(distanceMeters / Math.max(0.4, stepLengthMeters));
}

/**
 * Transforms raw object class into human actionable micro-context guidance.
 * RULE: Never just say "Chair ahead". Say "Empty chair at your 2 o'clock, 3 steps away. You can sit here."
 */
export function generateActionableGuidance(
  label: string,
  clockDirection: string,
  steps: number,
  zone: 'Left' | 'Center' | 'Right'
): string {
  const lowerLabel = label.toLowerCase();

  if (lowerLabel.includes('chair') || lowerLabel.includes('bench') || lowerLabel.includes('couch')) {
    return `Empty ${lowerLabel} at your ${clockDirection}, ${steps} steps away. You can sit here.`;
  }
  if (lowerLabel.includes('door') || lowerLabel.includes('entrance')) {
    return `Door handle is on your ${zone === 'Right' ? 'right' : 'left'} side, ${steps} steps ahead.`;
  }
  if (lowerLabel.includes('table') || lowerLabel.includes('desk')) {
    return `Table surface at your ${clockDirection}, ${steps} steps ahead.`;
  }
  if (lowerLabel.includes('car') || lowerLabel.includes('vehicle') || lowerLabel.includes('bus')) {
    return `Stop! Vehicle stationary at your ${clockDirection}, ${steps} steps.`;
  }
  if (lowerLabel.includes('person')) {
    return `Person walking at your ${clockDirection}, ${steps} steps ahead.`;
  }
  if (lowerLabel.includes('stair') || lowerLabel.includes('step down') || lowerLabel.includes('curb')) {
    return `Sidewalk curb coming up at your ${clockDirection} in ${steps} steps.`;
  }
  if (lowerLabel.includes('bottle') || lowerLabel.includes('cup')) {
    return `Item on surface at your ${clockDirection}, ${steps} steps away.`;
  }

  return `Obstacle detected at your ${clockDirection}, ${steps} steps ahead.`;
}

/**
 * Edge Rule Engine for Offline Navigation Alerts
 * Returns short, deterministic alert following Sahayak Drishti guidelines.
 */
export function processOfflineEdgeAlert(
  objects: DetectedObject[],
  ultrasonicCm: number,
  stepLengthMeters: number = 0.75
): { text: string; tier: CommunicationTier; chime: boolean } {
  const distanceMeters = ultrasonicCm / 100;
  const steps = calculateSteps(distanceMeters, stepLengthMeters);

  // Rule 1: Immediate Hazard (< 50cm or step down/vehicle hazard)
  if (ultrasonicCm > 0 && ultrasonicCm <= 50) {
    return {
      text: `Stop! Immediate obstacle ${steps} step ahead.`,
      tier: 'Tier 1',
      chime: false,
    };
  }

  // Find nearest object in center zone or closest overall
  const centerObjects = objects.filter((o) => o.zone === 'Center');
  const targetObj = centerObjects.length > 0 ? centerObjects[0] : objects[0];

  if (!targetObj) {
    // Silent rule: if path clear and no environmental change, REMAIN SILENT
    return {
      text: "SILENCE",
      tier: 'Tier 2',
      chime: false,
    };
  }

  const objSteps = calculateSteps(targetObj.distanceMeters, stepLengthMeters);

  if (targetObj.distanceMeters <= 1.2) {
    return {
      text: `Turn slightly ${targetObj.zone === 'Left' ? 'right' : 'left'}. ${targetObj.label} is ${objSteps} steps ahead at ${targetObj.clockDirection}.`,
      tier: 'Tier 2',
      chime: false,
    };
  }

  // Tier 3 Briefing or actionable note
  return {
    text: `[CHIME] ${targetObj.actionableNote}`,
    tier: 'Tier 3',
    chime: true,
  };
}
