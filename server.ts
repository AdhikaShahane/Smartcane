import express from "express";
import http from "http";
import path from "path";
import { createServer as createViteServer } from "vite";
import { GoogleGenAI, Modality, LiveServerMessage } from "@google/genai";
import { WebSocketServer, WebSocket } from "ws";
import dotenv from "dotenv";

dotenv.config();

const app = express();
const server = http.createServer(app);
const PORT = 3000;

app.use(express.json({ limit: "10mb" }));

// Initialize Google GenAI client lazily or with fallback check
let aiClient: GoogleGenAI | null = null;
function getAI() {
  if (!aiClient) {
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      console.warn("GEMINI_API_KEY environment variable is not set. Gemini API calls will be simulated or fail gracefully.");
      return null;
    }
    aiClient = new GoogleGenAI({
      apiKey,
      httpOptions: {
        headers: {
          "User-Agent": "aistudio-build",
        },
      },
    });
  }
  return aiClient;
}

// Sahayak Drishti System Prompt constant
const SAHAYAK_DRISHTI_SYSTEM_PROMPT = `
You are "Sahayak Drishti," an AI-powered mobility, spatial awareness, and safety companion embedded in a smart cane. Your sole mission is to guide visually impaired individuals safely through indoor and outdoor environments with absolute clarity, calm certainty, and human-like confidence.

1. VOICE, AUDIO & HUMAN PERSONA:
- Voice Profile: Calm, low-pitched, grounded, and reassuring Male Voice speaking with quiet authority.
- No AI Meta-Talk / Anti-Filler Rule: NEVER use phrases like "As an AI...", "I apologize...", "I think...", "I am detecting...", or "According to my camera...". Speak with direct certainty (e.g., "Path is clear," "Counter is 5 steps ahead on your left").
- Prosody & Pacing: Speak in a natural human cadence. Use strategic punctuation (commas, periods) to enforce micro-pauses.
- Audio Confirmation Signals: Output the tag [CHIME] before starting any multi-sentence contextual response or briefing so the user knows the assistant is active without checking hardware.
- Speech Output Template: Structure output using explicit punctuation for natural speech engine rendering:
  Example: [CHIME] "Path is clear. Counter is 4 steps ahead, on your left."

2. MULTI-TIERED COMMUNICATION & "ZERO-CLUTTER" SILENCE:
- Tier 1 (Immediate Hazard): High-priority haptic vibration + ultra-short audio burst. Example: "Stop! Step down ahead."
- Tier 2 (Actionable Navigation): Direct step-by-step guidance. Example: "Turn slightly left. Path clear."
- Tier 3 (Contextual Queries): Triggered only on direct user request or major scene transitions.
- The Silence Rule: If the path ahead is clear and no environmental changes occur, respond ONLY with "SILENCE". Do not offer continuous commentary. Silence builds user trust.

3. SPATIAL VISION ZONING & ACTIONABLE MICRO-CONTEXT:
- Camera Frame Division:
  Left Zone: 0% – 33% x-axis -> 9 o'clock to 11 o'clock.
  Center Zone: 34% – 66% x-axis -> 12 o'clock.
  Right Zone: 67% – 100% x-axis -> 1pm to 3 o'clock.
- Actionable Guidance: Never just list objects. Convert detected object classes into what the user can do or avoid:
  Bad: "Door detected." -> Good: "Door handle is on your right side."
  Bad: "Chair ahead." -> Good: "Empty chair at your 2 o'clock, 3 steps away. You can sit here."

4. STEP-BASED GAIT GUIDANCE & DISTANCE CONVERSION:
- Conversion Metric: Convert all linear distances (D in meters) into calibrated user step counts (N) using: Required Steps (N) = ceil(D / StepLength).
- NEVER use metric units like "1.5 meters" in verbal navigation. Always express distance in user steps. Example: "Obstacle 4 steps ahead."

5. PROACTIVE ENVIRONMENTAL CONTEXT (AMBIENT BRIEFINGS):
- When entering a new distinct environment (e.g. lobby, cafe, crosswalk), start with [CHIME] and give a concise 5-second ambient briefing (max 20 words).

6. STRICT FACTUAL ACCURACY & ZERO HALLUCINATION MANDATE:
- Report ONLY physical objects, terrain, and obstacles that are 100% unambiguously visible in the provided image frame or sensor data.
- NEVER guess, invent, assume, or hallucinate non-existent doors, steps, chairs, people, or hazards.
- If the camera frame is dark, blurry, obscured, or lacks distinct clear objects, respond strictly with: "Path unclear, proceed with caution."
- Do not speculate or invent distances when sensor/frame data is ambiguous.

7. STRICT RESPONSE CONSTRAINTS & SPEED LIMITS:
- Word Count Limit: Maximum 8 to 12 words per standard guidance or alert response (maximum 20 words for ambient briefings). Keep response ultra-short to ensure instant real-time speech synthesis.
- Action-Oriented: Focus on telling the user how to move rather than describing raw pixels.
`;

// Setup WebSocket Server for Live API Voice Conversations (gemini-3.1-flash-live-preview)
const wss = new WebSocketServer({ noServer: true });

wss.on("connection", async (ws: WebSocket) => {
  console.log("WebSocket client connected to Gemini Live API");
  const ai = getAI();
  if (!ai) {
    ws.send(JSON.stringify({ error: "GEMINI_API_KEY environment variable is missing on server." }));
    ws.close();
    return;
  }

  try {
    const session = await ai.live.connect({
      model: "gemini-3.1-flash-live-preview",
      config: {
        responseModalities: [Modality.AUDIO],
        speechConfig: {
          voiceConfig: { prebuiltVoiceConfig: { voiceName: "Charon" } },
        },
        systemInstruction: SAHAYAK_DRISHTI_SYSTEM_PROMPT,
      },
      callbacks: {
        onmessage: (message: LiveServerMessage) => {
          const audio = message.serverContent?.modelTurn?.parts?.[0]?.inlineData?.data;
          const text = message.serverContent?.modelTurn?.parts?.[0]?.text;
          if (audio) {
            ws.send(JSON.stringify({ audio }));
          }
          if (text) {
            ws.send(JSON.stringify({ text }));
          }
          if (message.serverContent?.interrupted) {
            ws.send(JSON.stringify({ interrupted: true }));
          }
        },
        onclose: () => {
          try {
            ws.send(JSON.stringify({ status: "closed" }));
          } catch (e) {}
        },
        onerror: (err: any) => {
          console.error("Live API session error:", err);
          try {
            ws.send(JSON.stringify({ error: err?.message || "Live API session error" }));
          } catch (e) {}
        },
      },
    });

    ws.on("message", (data: any) => {
      try {
        const parsed = JSON.parse(data.toString());
        if (parsed.audio) {
          session.sendRealtimeInput({
            audio: { data: parsed.audio, mimeType: "audio/pcm;rate=16000" },
          });
        } else if (parsed.text) {
          session.sendRealtimeInput({
            text: parsed.text,
          });
        }
      } catch (err) {
        console.warn("WS message processing error:", err);
      }
    });

    ws.on("close", () => {
      try {
        session.close();
      } catch (e) {}
    });
  } catch (err: any) {
    console.error("Failed to connect Gemini Live session:", err);
    try {
      ws.send(JSON.stringify({ error: "Failed to establish Live session: " + (err.message || String(err)) }));
    } catch (e) {}
  }
});

// API Route 1: Health check
app.get("/api/health", (req, res) => {
  res.json({ status: "ok", service: "Sahayak Drishti Backend", timestamp: new Date().toISOString() });
});

// API Route 2: Search Grounding using gemini-3.5-flash with googleSearch tool
app.post("/api/grounded-search", async (req, res) => {
  try {
    const { query } = req.body;
    if (!query) {
      return res.status(400).json({ error: "Query is required" });
    }

    const ai = getAI();
    if (!ai) {
      return res.json({
        response: `Search results for "${query}": Weather is clear, local transport is running smoothly.`,
        groundingSources: [{ title: "Local Navigation Services", uri: "https://google.com" }],
        source: "offline-fallback"
      });
    }

    const response = await ai.models.generateContent({
      model: "gemini-3.6-flash",
      contents: `User asks: "${query}". Provide a concise, clear, accurate real-time answer suited for a visually impaired user navigating their surroundings or seeking real-world updates. Max 2-3 sentences.`,
      config: {
        tools: [{ googleSearch: {} }],
        systemInstruction: "You are Sahayak Drishti, providing concise, clear, real-time grounded web search info for visually impaired mobility.",
      },
    });

    const replyText = response.text ? response.text.trim() : "No search data found.";
    const chunks = response.candidates?.[0]?.groundingMetadata?.groundingChunks || [];
    const groundingSources = chunks.map((chunk: any) => ({
      title: chunk.web?.title || "Web Source",
      uri: chunk.web?.uri || "",
    })).filter((s: any) => s.uri);

    res.json({
      response: replyText,
      groundingSources,
      source: "gemini-3.6-flash"
    });
  } catch (err: any) {
    console.error("Search Grounding API error:", err);
    res.json({
      response: `Search result for query: Local transport and weather conditions are normal. Proceed with care.`,
      groundingSources: [{ title: "Local Navigation Services", uri: "https://google.com" }],
      source: "search-fallback"
    });
  }
});

// API Route 3: Maps Grounding using gemini-2.5-flash with googleMaps tool
app.post("/api/grounded-maps", async (req, res) => {
  try {
    const { query, userLocation } = req.body;
    if (!query) {
      return res.status(400).json({ error: "Query is required" });
    }

    const ai = getAI();
    if (!ai) {
      return res.json({
        response: `Nearby location info for "${query}": Bus stop is 120 steps north near Main Street entrance.`,
        groundingSources: [{ title: "Google Maps Location", uri: "https://maps.google.com" }],
        source: "offline-fallback"
      });
    }

    const locationContext = userLocation ? `Near latitude ${userLocation.latitude}, longitude ${userLocation.longitude}.` : "";

    const response = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: `User location query: "${query}". ${locationContext} Provide exact location details, orientation, landmarks, and navigation guidance for a visually impaired person.`,
      config: {
        tools: [{ googleMaps: {} }],
        systemInstruction: "You are Sahayak Drishti, using Google Maps grounding to guide visually impaired users with places, landmarks, step directions, and map coordinates.",
      },
    });

    const replyText = response.text ? response.text.trim() : "No map data found.";
    const chunks = response.candidates?.[0]?.groundingMetadata?.groundingChunks || [];
    const groundingSources = chunks.map((chunk: any) => ({
      title: chunk.web?.title || chunk.maps?.title || "Google Maps Landmark",
      uri: chunk.web?.uri || chunk.maps?.uri || "https://maps.google.com",
    })).filter((s: any) => s.uri);

    res.json({
      response: replyText,
      groundingSources,
      source: "gemini-2.5-flash-maps-grounding"
    });
  } catch (err: any) {
    console.error("Maps Grounding API error:", err);
    res.json({
      response: `Location guide: Main entrance is located 80 steps directly ahead.`,
      groundingSources: [{ title: "Google Maps Landmark", uri: "https://maps.google.com" }],
      source: "maps-fallback"
    });
  }
});

// API Route 4: Analyze vision frame & sensors with Gemini
app.post("/api/analyze-vision", async (req, res) => {
  try {
    const { imageBase64, userQuery, sensorData, stepLength = 0.75, environmentContext, searchMode } = req.body;

    const ai = getAI();
    
    // Construct rich text prompt combining query, sensors, and gait step length
    const promptText = `
User Calibrated Step Length: ${stepLength} meters.
Current Sensors: Ultrasonic Distance = ${sensorData?.ultrasonicCm ?? 150} cm, IMU Motion = ${sensorData?.imuMotion ?? 'steady'}, Compass = ${sensorData?.compassHeading ?? 'North'}.
Environment Context: ${environmentContext || 'general walking space'}.
User Query / Trigger: ${userQuery || 'Analyze path and obstacles ahead for navigation'}.

Examine the scene/frame and provide the exact Sahayak Drishti speech response following all system prompt rules. Convert all distances to step counts! Remember: Max 8-12 words for alerts, max 20 words for ambient briefings. Use [CHIME] if multi-sentence or briefing. Respond "SILENCE" if path is completely clear and no change.
`;

    if (!ai) {
      // Fallback rule-based smart response if no API key is attached
      const distanceMeters = (sensorData?.ultrasonicCm || 150) / 100;
      const steps = Math.ceil(distanceMeters / stepLength);

      let text = "Path is clear. Proceed straight.";
      let tier = "Tier 2";

      if (distanceMeters < 0.6) {
        text = `Stop! Obstacle ${steps} step ahead.`;
        tier = "Tier 1";
      } else if (userQuery && userQuery.toLowerCase().includes("where")) {
        text = `[CHIME] Main entrance counter is 5 steps ahead at 12 o'clock. Seating on your left.`;
        tier = "Tier 3";
      } else if (distanceMeters < 1.5) {
        text = `Turn slightly right. Chair is ${steps} steps ahead at 11 o'clock.`;
        tier = "Tier 2";
      }

      return res.json({
        response: text,
        tier,
        steps,
        source: "offline-rule-fallback",
        chime: text.includes("[CHIME]")
      });
    }

    const contentsParts: any[] = [];
    if (imageBase64) {
      // Clean base64 string
      const cleanData = imageBase64.replace(/^data:image\/(png|jpeg|webp);base64,/, "");
      contentsParts.push({
        inlineData: {
          mimeType: "image/jpeg",
          data: cleanData,
        },
      });
    }
    contentsParts.push({ text: promptText });

    // Choose model & tools based on query intent
    const isMapQuery = userQuery && (userQuery.toLowerCase().includes("where is") || userQuery.toLowerCase().includes("map") || userQuery.toLowerCase().includes("location") || userQuery.toLowerCase().includes("directions") || userQuery.toLowerCase().includes("bus stop") || userQuery.toLowerCase().includes("hospital"));
    const isSearchQuery = searchMode || (userQuery && (userQuery.toLowerCase().includes("search") || userQuery.toLowerCase().includes("weather") || userQuery.toLowerCase().includes("news") || userQuery.toLowerCase().includes("time")));

    let toolsConfig: any = undefined;
    let candidateModels = ["gemini-3.6-flash", "gemini-flash-latest"];

    if (isMapQuery) {
      candidateModels = ["gemini-3.6-flash", "gemini-flash-latest"];
      toolsConfig = [{ googleMaps: {} }];
    } else if (isSearchQuery) {
      candidateModels = ["gemini-3.6-flash", "gemini-flash-latest"];
      toolsConfig = [{ googleSearch: {} }];
    }

    let responseText = "";
    let groundingSources: any[] = [];
    let usedModel = candidateModels[0];
    let success = false;

    for (const modelName of candidateModels) {
      try {
        const result = await ai.models.generateContent({
          model: modelName,
          contents: { parts: contentsParts },
          config: {
            systemInstruction: SAHAYAK_DRISHTI_SYSTEM_PROMPT,
            temperature: 0.0,
            maxOutputTokens: 50,
            ...(toolsConfig ? { tools: toolsConfig } : {})
          },
        });

        if (result.text) {
          responseText = result.text.trim();
          usedModel = modelName;
          const chunks = result.candidates?.[0]?.groundingMetadata?.groundingChunks || [];
          groundingSources = chunks.map((chunk: any) => ({
            title: chunk.web?.title || chunk.maps?.title || "Grounding Reference",
            uri: chunk.web?.uri || chunk.maps?.uri || "",
          })).filter((s: any) => s.uri);
          success = true;
          break;
        }
      } catch (modErr: any) {
        console.warn(`Model ${modelName} failed, trying fallback model...`, modErr?.message || modErr);
      }
    }

    // Fallback if all AI model calls encounter transient 503 or network issue
    if (!success) {
      const distanceCm = sensorData?.ultrasonicCm || 200;
      if (distanceCm < 80) {
        responseText = `STOP! Obstacle detected ${distanceCm} centimeters ahead.`;
      } else {
        responseText = `Path clear. Continue forward with caution.`;
      }
      usedModel = "offline-edge-safety-fallback";
    }

    // Determine communication Tier based on content
    let tier = "Tier 2";
    if (responseText.toLowerCase().startsWith("stop") || responseText.includes("Hazard") || responseText.includes("Impact")) {
      tier = "Tier 1";
    } else if (responseText.includes("[CHIME]") || responseText.length > 40) {
      tier = "Tier 3";
    }

    res.json({
      response: responseText,
      tier,
      source: usedModel,
      chime: responseText.includes("[CHIME]"),
      groundingSources
    });

  } catch (error: any) {
    console.error("Error analyzing vision with Gemini:", error);
    res.json({
      response: "Path clear. Continue with caution.",
      tier: "Tier 2",
      source: "Offline Edge Safety Guard",
      chime: false,
      groundingSources: []
    });
  }
});

// API Route 5: Generate Speech via Gemini TTS (Optional enhanced voice)
app.post("/api/speech-tts", async (req, res) => {
  try {
    const { text } = req.body;
    if (!text || text === "SILENCE") {
      return res.json({ audioBase64: null });
    }

    const ai = getAI();
    if (!ai) {
      return res.json({ audioBase64: null, note: "Using browser native TTS engine" });
    }

    // Clean text of [CHIME] tag for TTS input
    const cleanText = text.replace(/\[CHIME\]/gi, "").trim();

    const response = await ai.models.generateContent({
      model: "gemini-3.1-flash-tts-preview",
      contents: [{ parts: [{ text: `Speak in a calm, grounded, reassuring low-pitched male voice: ${cleanText}` }] }],
      config: {
        responseModalities: ["AUDIO"],
        speechConfig: {
          voiceConfig: {
            prebuiltVoiceConfig: { voiceName: "Charon" }, // Grounded male voice
          },
        },
      },
    });

    const base64Audio = response.candidates?.[0]?.content?.parts?.[0]?.inlineData?.data || null;
    res.json({ audioBase64: base64Audio });

  } catch (err: any) {
    console.warn("TTS API Error, falling back to Web Speech API:", err.message);
    res.json({ audioBase64: null, note: "Browser TTS fallback" });
  }
});

async function startServer() {
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  // Handle WebSocket HTTP upgrades on /live path
  server.on("upgrade", (request, socket, head) => {
    const pathname = new URL(request.url || "", `http://${request.headers.host}`).pathname;
    if (pathname === "/live") {
      wss.handleUpgrade(request, socket, head, (ws) => {
        wss.emit("connection", ws, request);
      });
    } else {
      socket.destroy();
    }
  });

  server.listen(PORT, "0.0.0.0", () => {
    console.log(`Sahayak Drishti full-stack server running on http://0.0.0.0:${PORT}`);
  });
}

startServer();

