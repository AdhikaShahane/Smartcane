import React, { useState, useEffect, useRef } from "react";
import { Mic, MicOff, Radio, Volume2, Shield, Sparkles, Activity, AlertCircle, RefreshCw } from "lucide-react";

interface LiveVoiceConversationProps {
  onClose?: () => void;
}

export const LiveVoiceConversation: React.FC<LiveVoiceConversationProps> = () => {
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [transcripts, setTranscripts] = useState<Array<{ sender: "user" | "model"; text: string }>>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const inputAudioCtxRef = useRef<AudioContext | null>(null);
  const outputAudioCtxRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const scriptProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const nextStartTimeRef = useRef<number>(0);

  // Connect to Gemini Live WebSocket
  const startLiveSession = async () => {
    setErrorMsg(null);
    setIsConnecting(true);

    try {
      // 1. Establish WebSocket connection to backend live endpoint
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${protocol}//${window.location.host}/live`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = async () => {
        setIsConnected(true);
        setIsConnecting(false);
        setTranscripts((prev) => [
          ...prev,
          { sender: "model", text: "[CHIME] Live voice conversation connected with Sahayak Drishti. Speak naturally." },
        ]);

        // Start capturing 16kHz mic input
        await startMicCapture(ws);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.error) {
            setErrorMsg(data.error);
            return;
          }

          if (data.audio) {
            playAudioChunk(data.audio);
          }

          if (data.text) {
            setTranscripts((prev) => {
              const last = prev[prev.length - 1];
              if (last && last.sender === "model") {
                return [...prev.slice(0, -1), { sender: "model", text: last.text + data.text }];
              }
              return [...prev, { sender: "model", text: data.text }];
            });
          }

          if (data.interrupted) {
            nextStartTimeRef.current = 0;
          }
        } catch (err) {
          console.warn("Live WS message parse error:", err);
        }
      };

      ws.onerror = (e) => {
        console.error("Live WS error:", e);
        setErrorMsg("Live Voice connection error. Reconnecting...");
        setIsConnected(false);
        setIsConnecting(false);
      };

      ws.onclose = () => {
        setIsConnected(false);
        setIsConnecting(false);
        stopMicCapture();
      };
    } catch (err: any) {
      console.error("Live session failed:", err);
      setErrorMsg(err.message || "Failed to start Live API session.");
      setIsConnecting(false);
      setIsConnected(false);
    }
  };

  // Capture 16kHz PCM audio from microphone
  const startMicCapture = async (ws: WebSocket) => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: 16000,
        },
      });
      mediaStreamRef.current = stream;

      const inputCtx = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 });
      inputAudioCtxRef.current = inputCtx;

      const source = inputCtx.createMediaStreamSource(stream);
      const processor = inputCtx.createScriptProcessor(4096, 1, 1);
      scriptProcessorRef.current = processor;

      source.connect(processor);
      processor.connect(inputCtx.destination);

      processor.onaudioprocess = (e) => {
        if (isMuted || !ws || ws.readyState !== WebSocket.OPEN) return;

        const channelData = e.inputBuffer.getChannelData(0);

        // Compute audio level for UI visualizer
        let sum = 0;
        for (let i = 0; i < channelData.length; i++) {
          sum += channelData[i] * channelData[i];
        }
        const rms = Math.sqrt(sum / channelData.length);
        setAudioLevel(Math.min(100, Math.round(rms * 400)));

        // Convert Float32 (-1.0 to +1.0) to Int16 PCM
        const pcm16 = new Int16Array(channelData.length);
        for (let i = 0; i < channelData.length; i++) {
          const s = Math.max(-1, Math.min(1, channelData[i]));
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }

        // Convert Int16Array buffer to Base64
        const uint8 = new Uint8Array(pcm16.buffer);
        let binary = "";
        for (let i = 0; i < uint8.byteLength; i++) {
          binary += String.fromCharCode(uint8[i]);
        }
        const base64Audio = btoa(binary);

        ws.send(JSON.stringify({ audio: base64Audio }));
      };
    } catch (err: any) {
      console.error("Mic capture error:", err);
      setErrorMsg("Microphone access denied or unavailable for Live voice.");
    }
  };

  // Playback 24kHz PCM output from Live API
  const playAudioChunk = (base64Pcm: string) => {
    try {
      if (!outputAudioCtxRef.current) {
        outputAudioCtxRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({
          sampleRate: 24000,
        });
      }
      const outputCtx = outputAudioCtxRef.current;
      if (outputCtx.state === "suspended") {
        outputCtx.resume();
      }

      const binary = atob(base64Pcm);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
      }

      const int16 = new Int16Array(bytes.buffer);
      const float32 = new Float32Array(int16.length);
      for (let i = 0; i < int16.length; i++) {
        float32[i] = int16[i] / (int16[i] < 0 ? 32768 : 32767);
      }

      const buffer = outputCtx.createBuffer(1, float32.length, 24000);
      buffer.getChannelData(0).set(float32);

      const source = outputCtx.createBufferSource();
      source.buffer = buffer;
      source.connect(outputCtx.destination);

      const currentTime = outputCtx.currentTime;
      const startTime = Math.max(currentTime, nextStartTimeRef.current);
      source.start(startTime);
      nextStartTimeRef.current = startTime + buffer.duration;
    } catch (err) {
      console.warn("PCM audio playback error:", err);
    }
  };

  const stopMicCapture = () => {
    if (scriptProcessorRef.current) {
      scriptProcessorRef.current.disconnect();
      scriptProcessorRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    if (inputAudioCtxRef.current) {
      inputAudioCtxRef.current.close();
      inputAudioCtxRef.current = null;
    }
    setAudioLevel(0);
  };

  const endLiveSession = () => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    stopMicCapture();
    setIsConnected(false);
    setIsConnecting(false);
  };

  useEffect(() => {
    return () => {
      endLiveSession();
    };
  }, []);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-2xl flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="p-2 bg-emerald-500/10 rounded-xl border border-emerald-500/30 text-emerald-400">
            <Radio className={`w-5 h-5 ${isConnected ? "animate-pulse" : ""}`} />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              Gemini Live Voice Conversation
              <span className="text-[10px] font-mono bg-emerald-950 text-emerald-400 border border-emerald-800/80 px-2 py-0.5 rounded-full">
                gemini-3.1-flash-live-preview
              </span>
            </h3>
            <p className="text-xs text-slate-400">
              Low-latency continuous real-time audio interaction with Sahayak Drishti
            </p>
          </div>
        </div>

        {/* Action Button */}
        <div>
          {!isConnected ? (
            <button
              onClick={startLiveSession}
              disabled={isConnecting}
              className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-semibold px-4 py-2 rounded-xl transition flex items-center gap-2 shadow-lg shadow-emerald-900/40"
            >
              {isConnecting ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  Connecting...
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5" />
                  Start Live Voice Mode
                </>
              )}
            </button>
          ) : (
            <button
              onClick={endLiveSession}
              className="bg-red-900/80 hover:bg-red-800 text-red-100 border border-red-700/60 text-xs font-semibold px-4 py-2 rounded-xl transition flex items-center gap-2"
            >
              <MicOff className="w-3.5 h-3.5 text-red-300" />
              Disconnect Live Mode
            </button>
          )}
        </div>
      </div>

      {/* Error display */}
      {errorMsg && (
        <div className="bg-red-950/80 border border-red-800 text-red-200 text-xs p-3 rounded-xl flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Live Audio Visualizer Bar */}
      {isConnected && (
        <div className="bg-slate-950 border border-slate-800/80 rounded-xl p-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs font-mono text-slate-300">
            <Activity className="w-4 h-4 text-emerald-400 animate-pulse" />
            <span>MIC SIGNAL:</span>
            <div className="w-32 h-2.5 bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-emerald-400 transition-all duration-75"
                style={{ width: `${audioLevel}%` }}
              />
            </div>
          </div>

          <button
            onClick={() => setIsMuted(!isMuted)}
            className={`px-3 py-1 text-xs rounded-lg font-mono flex items-center gap-1.5 transition ${
              isMuted
                ? "bg-red-950 text-red-400 border border-red-800"
                : "bg-slate-800 text-slate-200 border border-slate-700 hover:bg-slate-700"
            }`}
          >
            {isMuted ? <MicOff className="w-3.5 h-3.5" /> : <Mic className="w-3.5 h-3.5 text-emerald-400" />}
            {isMuted ? "MUTED" : "MIC ACTIVE"}
          </button>
        </div>
      )}

      {/* Live Transcript Stream Box */}
      <div className="bg-slate-950 border border-slate-800/80 rounded-xl p-3.5 max-h-44 overflow-y-auto space-y-2 font-sans text-xs">
        {transcripts.length === 0 ? (
          <div className="text-slate-500 text-center py-4 italic flex flex-col items-center gap-1">
            <Volume2 className="w-5 h-5 text-slate-600 mb-1" />
            <span>Click "Start Live Voice Mode" to speak continuously with Sahayak Drishti.</span>
          </div>
        ) : (
          transcripts.map((t, idx) => (
            <div
              key={idx}
              className={`p-2.5 rounded-xl ${
                t.sender === "user"
                  ? "bg-slate-800 text-slate-100 ml-6 border border-slate-700"
                  : "bg-emerald-950/40 text-emerald-200 mr-6 border border-emerald-800/50"
              }`}
            >
              <span className="font-bold text-[10px] block opacity-70 mb-0.5 uppercase tracking-wider">
                {t.sender === "user" ? "You (Voice)" : "Sahayak Live API"}
              </span>
              {t.text}
            </div>
          ))
        )}
      </div>
    </div>
  );
};
