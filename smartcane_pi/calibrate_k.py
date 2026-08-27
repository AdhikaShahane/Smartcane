#!/usr/bin/env python3
"""
SmartCane K-Factor Gait Calibration Tool
Calculates user-specific K constant using:
K = (Measured_Distance / Total_Steps) / ((a_max - a_min) ^ (1/4))
"""

import sys
import math

def run_calibration():
    print("==================================================")
    print("      SMARTCANE K-CONSTANT CALIBRATION TOOL       ")
    print("==================================================")
    print("Formula: SL = K * (a_max - a_min)^(1/4)")
    print("Equivalent: K = Measured_Step_Length / (a_diff)^(0.25)\n")

    try:
        dist_str = input("Enter walking test distance in meters (e.g. 10.0): ").strip()
        dist = float(dist_str) if dist_str else 10.0

        steps_str = input("Enter number of steps taken to walk this distance (e.g. 15): ").strip()
        steps = int(steps_str) if steps_str else 15

        diff_str = input("Enter average (a_max - a_min) in m/s^2 (default 1.8): ").strip()
        a_diff = float(diff_str) if diff_str else 1.8

        measured_sl = dist / steps
        fourth_root = a_diff ** 0.25
        k_val = measured_sl / fourth_root

        print("\n---------------- CALIBRATION RESULT ----------------")
        print(f"Measured Average Step Length : {measured_sl:.3f} meters")
        print(f"Acceleration Difference (a_diff) : {a_diff:.2f} m/s²")
        print(f"Calculated ⁴√(a_diff)       : {fourth_root:.3f}")
        print(f"==> Recommended K Constant  : {k_val:.3f}")
        print("----------------------------------------------------")
        print(f"\nUpdate SmartCaneConfig.CALIBRATION_K = {k_val:.3f} in smartcane_service.py")
    except Exception as e:
        print(f"Error during calibration: {e}")

if __name__ == "__main__":
    run_calibration()
