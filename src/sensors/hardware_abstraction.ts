/**
 * Hardware Abstraction Layer (HAL)
 * 
 * Distinguishes between DEVELOPMENT MODE (USB webcam, PC mic, browser audio, simulated sensors)
 * and REAL RASPBERRY PI HARDWARE MODE (I2C MPU6050, GPIO HC-SR04, Pi Camera V4L2/Picamera2, ALSA audio, serial GPS).
 */

export interface HardwareInterfaces {
  mode: 'DEVELOPMENT' | 'RASPBERRY_PI';
  cameraReady: boolean;
  microphoneReady: boolean;
  speakerReady: boolean;
  mpu6050Ready: boolean;
  ultrasonicReady: boolean;
  gpsReady: boolean;
  esp32BridgeReady: boolean;
}

export class HardwareAbstractionLayer {
  private currentMode: 'DEVELOPMENT' | 'RASPBERRY_PI' = 'DEVELOPMENT';
  private interfaces: HardwareInterfaces = {
    mode: 'DEVELOPMENT',
    cameraReady: true,
    microphoneReady: true,
    speakerReady: true,
    mpu6050Ready: true,
    ultrasonicReady: true,
    gpsReady: true,
    esp32BridgeReady: false
  };

  public setMode(mode: 'DEVELOPMENT' | 'RASPBERRY_PI') {
    this.currentMode = mode;
    this.interfaces.mode = mode;
  }

  public getMode(): 'DEVELOPMENT' | 'RASPBERRY_PI' {
    return this.currentMode;
  }

  public getInterfaces(): HardwareInterfaces {
    return { ...this.interfaces };
  }

  public updateInterfaceStatus(key: keyof HardwareInterfaces, value: boolean) {
    if (key !== 'mode') {
      (this.interfaces as any)[key] = value;
    }
  }
}

export const hal = new HardwareAbstractionLayer();
