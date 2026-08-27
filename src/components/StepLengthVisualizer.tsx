import React, { useState, useEffect } from "react";
import { Activity, Sliders, Calculator, Footprints, Check, RefreshCw } from "lucide-react";
import { stepCalculator } from "../navigation/step_length_calculator";
import { mpuProcessor } from "../sensors/mpu6050_processor";
import { StepIntervalData } from "../core/types";

interface StepLengthVisualizerProps {
  currentStepInterval: StepIntervalData;
  onKChange: (newK: number) => void;
}

export const StepLengthVisualizer: React.FC<StepLengthVisualizerProps> = ({
  currentStepInterval,
  onKChange
}) => {
  const [kConstant, setKConstant] = useState<number>(currentStepInterval.calibrationK || 0.45);
  const [testDistance, setTestDistance] = useState<number>(2.4); // meters
  const [isCalibrating, setIsCalibrating] = useState<boolean>(false);
  const [calibDistance, setCalibDistance] = useState<number>(10.0);
  const [calibSteps, setCalibSteps] = useState<number>(15);
  const [calibSuccess, setCalibSuccess] = useState<string | null>(null);

  // Sync state with prop
  useEffect(() => {
    if (currentStepInterval.calibrationK && currentStepInterval.calibrationK !== kConstant) {
      setKConstant(currentStepInterval.calibrationK);
    }
  }, [currentStepInterval.calibrationK]);

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    setKConstant(val);
    stepCalculator.setCalibrationK(val);
    onKChange(val);
  };

  const handleCalibrate = (e: React.FormEvent) => {
    e.preventDefault();
    const newK = stepCalculator.calibrateFromTest(
      calibDistance,
      calibSteps,
      currentStepInterval.aDiff > 0 ? currentStepInterval.aDiff : 1.8
    );
    setKConstant(newK);
    onKChange(newK);
    setCalibSuccess(`Calibrated K = ${newK.toFixed(3)} for ${calibSteps} steps in ${calibDistance}m`);
    setTimeout(() => {
      setIsCalibrating(false);
      setCalibSuccess(null);
    }, 2500);
  };

  const calculatedSteps = stepCalculator.convertDistanceToSteps(testDistance, currentStepInterval.stepLengthMeters);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 text-white shadow-xl flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-400">
            <Footprints className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              MPU6050 Gait & Step-Length Engine
              <span className="px-2 py-0.5 text-[10px] font-mono rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                ACTIVE
              </span>
            </h3>
            <p className="text-xs text-slate-400">
              Formula: <code className="font-mono text-amber-300 font-semibold">SL = K × ⁴√(a_max − a_min)</code>
            </p>
          </div>
        </div>

        <button
          onClick={() => setIsCalibrating(!isCalibrating)}
          className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition flex items-center gap-1.5"
        >
          <Sliders className="w-3.5 h-3.5 text-amber-400" />
          {isCalibrating ? "Close Calibration" : "Calibrate K"}
        </button>
      </div>

      {/* Main Formula Dashboard Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {/* Metric 1: a_max */}
        <div className="bg-slate-950/80 rounded-xl p-3 border border-slate-800 flex flex-col justify-between">
          <span className="text-[11px] font-mono text-slate-400">Peak Accel (a_max)</span>
          <div className="text-lg font-bold font-mono text-cyan-400 mt-1">
            {currentStepInterval.aMax.toFixed(2)} <span className="text-xs text-slate-500 font-sans">m/s²</span>
          </div>
          <span className="text-[10px] text-slate-500 mt-1">Gait peak</span>
        </div>

        {/* Metric 2: a_min */}
        <div className="bg-slate-950/80 rounded-xl p-3 border border-slate-800 flex flex-col justify-between">
          <span className="text-[11px] font-mono text-slate-400">Valley Accel (a_min)</span>
          <div className="text-lg font-bold font-mono text-purple-400 mt-1">
            {currentStepInterval.aMin.toFixed(2)} <span className="text-xs text-slate-500 font-sans">m/s²</span>
          </div>
          <span className="text-[10px] text-slate-500 mt-1">Gait valley</span>
        </div>

        {/* Metric 3: (a_max - a_min)^(1/4) */}
        <div className="bg-slate-950/80 rounded-xl p-3 border border-slate-800 flex flex-col justify-between">
          <span className="text-[11px] font-mono text-slate-400">⁴√(a_max − a_min)</span>
          <div className="text-lg font-bold font-mono text-sky-300 mt-1">
            {currentStepInterval.fourthRootDiff.toFixed(3)}
          </div>
          <span className="text-[10px] text-slate-500 mt-1">Diff: {currentStepInterval.aDiff.toFixed(2)}</span>
        </div>

        {/* Metric 4: Calculated Step Length SL */}
        <div className="bg-amber-500/10 rounded-xl p-3 border border-amber-500/40 flex flex-col justify-between">
          <span className="text-[11px] font-mono text-amber-300 font-semibold">Personalized SL</span>
          <div className="text-xl font-bold font-mono text-amber-400 mt-1">
            {currentStepInterval.stepLengthMeters.toFixed(3)} <span className="text-xs text-amber-300 font-sans">m</span>
          </div>
          <span className="text-[10px] text-amber-200/70 mt-1">K = {kConstant.toFixed(2)}</span>
        </div>
      </div>

      {/* K Calibration Slider */}
      <div className="bg-slate-950/60 rounded-xl p-3.5 border border-slate-800/80 flex flex-col gap-2">
        <div className="flex items-center justify-between text-xs">
          <span className="font-semibold text-slate-300 flex items-center gap-1.5">
            <Sliders className="w-3.5 h-3.5 text-amber-400" />
            Calibration Constant (K):
          </span>
          <span className="font-mono font-bold text-amber-400 text-sm">{kConstant.toFixed(2)}</span>
        </div>
        <input
          type="range"
          min="0.20"
          max="0.80"
          step="0.01"
          value={kConstant}
          onChange={handleSliderChange}
          className="w-full accent-amber-500 cursor-pointer"
        />
        <div className="flex justify-between text-[10px] text-slate-500 font-mono">
          <span>0.20 (Short Gait)</span>
          <span>0.45 (Default Standard)</span>
          <span>0.80 (Long Gait)</span>
        </div>
      </div>

      {/* Interactive Distance-to-Steps Conversion Demo */}
      <div className="bg-slate-950/90 rounded-xl p-4 border border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex-1 w-full">
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span className="font-semibold text-slate-300 flex items-center gap-1.5">
              <Calculator className="w-3.5 h-3.5 text-emerald-400" />
              Distance-to-Steps Conversion Sandbox:
            </span>
            <span className="font-mono text-slate-400">D = {testDistance.toFixed(1)}m</span>
          </div>
          <input
            type="range"
            min="0.5"
            max="10.0"
            step="0.1"
            value={testDistance}
            onChange={(e) => setTestDistance(parseFloat(e.target.value))}
            className="w-full accent-emerald-500 cursor-pointer"
          />
        </div>

        <div className="flex items-center gap-3 bg-slate-900 border border-slate-800 px-4 py-2 rounded-xl text-center">
          <div className="text-left">
            <div className="text-[10px] text-slate-400 uppercase tracking-wider font-mono">Formula: D / SL</div>
            <div className="text-xs text-slate-300">
              {testDistance.toFixed(1)}m / {currentStepInterval.stepLengthMeters.toFixed(2)}m
            </div>
          </div>
          <div className="text-2xl font-bold font-mono text-emerald-400">
            {calculatedSteps} <span className="text-xs font-sans text-emerald-300">steps</span>
          </div>
        </div>
      </div>

      {/* Calibration Sub-panel (if opened) */}
      {isCalibrating && (
        <form onSubmit={handleCalibrate} className="bg-amber-950/30 border border-amber-500/40 rounded-xl p-4 flex flex-col gap-3">
          <h4 className="text-xs font-bold text-amber-300 flex items-center gap-1.5">
            <Activity className="w-4 h-4" />
            Walk-Test Calibration Wizard
          </h4>
          <p className="text-xs text-slate-300">
            Walk a measured line (e.g., 10 meters) and count your steps. The system will compute your personalized K constant.
          </p>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">Measured Distance (meters)</label>
              <input
                type="number"
                step="0.5"
                min="3"
                max="50"
                value={calibDistance}
                onChange={(e) => setCalibDistance(parseFloat(e.target.value))}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white"
              />
            </div>
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">Total Steps Counted</label>
              <input
                type="number"
                min="4"
                max="100"
                value={calibSteps}
                onChange={(e) => setCalibSteps(parseInt(e.target.value))}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white"
              />
            </div>
          </div>

          <div className="flex items-center justify-between pt-1">
            {calibSuccess ? (
              <span className="text-xs text-emerald-400 font-medium flex items-center gap-1">
                <Check className="w-3.5 h-3.5" />
                {calibSuccess}
              </span>
            ) : (
              <span className="text-[11px] text-slate-400 font-mono">
                Avg Step: {(calibDistance / (calibSteps || 1)).toFixed(2)}m
              </span>
            )}
            <button
              type="submit"
              className="px-4 py-1.5 bg-amber-600 hover:bg-amber-500 text-slate-950 font-bold rounded-lg text-xs transition"
            >
              Apply Calibration
            </button>
          </div>
        </form>
      )}
    </div>
  );
};
