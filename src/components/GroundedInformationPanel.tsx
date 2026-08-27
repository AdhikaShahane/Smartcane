import React, { useState } from "react";
import { Search, MapPin, Globe, ExternalLink, Sparkles, Navigation, Loader2 } from "lucide-react";

interface GroundingSource {
  title: string;
  uri: string;
}

interface GroundedInformationPanelProps {
  onSpeakText?: (text: string) => void;
}

export const GroundedInformationPanel: React.FC<GroundedInformationPanelProps> = ({ onSpeakText }) => {
  const [activeTab, setActiveTab] = useState<"search" | "maps">("search");
  const [query, setQuery] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [response, setResponse] = useState<string | null>(null);
  const [sources, setSources] = useState<GroundingSource[]>([]);
  const [groundingSourceType, setGroundingSourceType] = useState<string | null>(null);

  const handleRunSearch = async (overrideQuery?: string) => {
    const q = overrideQuery || query;
    if (!q.trim()) return;

    setIsLoading(true);
    setResponse(null);
    setSources([]);

    try {
      const endpoint = activeTab === "search" ? "/api/grounded-search" : "/api/grounded-maps";
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q }),
      });
      const data = await res.json();

      if (data.response) {
        setResponse(data.response);
        setSources(data.groundingSources || []);
        setGroundingSourceType(data.source || (activeTab === "search" ? "gemini-3.5-flash-search" : "gemini-3.5-flash-maps"));

        if (onSpeakText && data.response) {
          onSpeakText(data.response);
        }
      } else {
        setResponse("No grounded information returned for this query.");
      }
    } catch (err) {
      console.error("Grounding query failed:", err);
      setResponse("Failed to fetch grounded info. Please verify network connection.");
    } finally {
      setIsLoading(false);
    }
  };

  const sampleSearchQueries = [
    "What is the weather forecast for navigation today?",
    "Local public bus routes and real-time transit schedule",
    "Latest accessibility updates for city sidewalks",
  ];

  const sampleMapQueries = [
    "Find nearest accessible bus stop and entrance steps",
    "Where is the nearest hospital or urgent care center?",
    "Step-by-step walking path to the nearest metro station",
  ];

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl flex flex-col gap-4">
      {/* Mode Switch Tabs */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-1.5 bg-slate-950 p-1 rounded-xl border border-slate-800">
          <button
            onClick={() => {
              setActiveTab("search");
              setResponse(null);
            }}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition flex items-center gap-1.5 ${
              activeTab === "search"
                ? "bg-indigo-600 text-white shadow-md shadow-indigo-950"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Globe className="w-3.5 h-3.5 text-indigo-300" />
            <span>Google Search Grounding</span>
          </button>

          <button
            onClick={() => {
              setActiveTab("maps");
              setResponse(null);
            }}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition flex items-center gap-1.5 ${
              activeTab === "maps"
                ? "bg-emerald-600 text-white shadow-md shadow-emerald-950"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <MapPin className="w-3.5 h-3.5 text-emerald-300" />
            <span>Google Maps Grounding</span>
          </button>
        </div>

        <span className="text-[10px] font-mono text-slate-400 bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-800">
          Model: <span className="text-amber-400 font-bold">gemini-3.5-flash</span>
        </span>
      </div>

      {/* Query Input Form */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleRunSearch()}
            placeholder={
              activeTab === "search"
                ? "Search real-time weather, transit, or web info..."
                : "Find nearby landmarks, bus stops, or map locations..."
            }
            className="w-full bg-slate-950 border border-slate-800 text-slate-100 text-xs rounded-xl px-4 py-3 pl-9 focus:outline-none focus:border-indigo-500 placeholder-slate-500 font-medium"
          />
          {activeTab === "search" ? (
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-3.5" />
          ) : (
            <Navigation className="w-4 h-4 text-slate-500 absolute left-3 top-3.5" />
          )}
        </div>

        <button
          onClick={() => handleRunSearch()}
          disabled={isLoading || !query.trim()}
          className={`px-4 py-3 rounded-xl text-xs font-semibold text-white transition flex items-center gap-1.5 disabled:opacity-50 ${
            activeTab === "search" ? "bg-indigo-600 hover:bg-indigo-500" : "bg-emerald-600 hover:bg-emerald-500"
          }`}
        >
          {isLoading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <>
              <Sparkles className="w-4 h-4" />
              Fetch Info
            </>
          )}
        </button>
      </div>

      {/* Preset Example Quick Prompt Chips */}
      <div className="flex flex-wrap gap-1.5">
        <span className="text-[11px] text-slate-400 self-center mr-1 font-mono">Presets:</span>
        {(activeTab === "search" ? sampleSearchQueries : sampleMapQueries).map((qText, i) => (
          <button
            key={i}
            onClick={() => {
              setQuery(qText);
              handleRunSearch(qText);
            }}
            className="text-[11px] bg-slate-950 border border-slate-800 text-slate-300 hover:text-white hover:border-slate-700 px-2.5 py-1 rounded-lg transition"
          >
            {qText}
          </button>
        ))}
      </div>

      {/* Answer Output & Citations */}
      {response && (
        <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 flex flex-col gap-3 font-sans text-xs text-slate-200">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
            <span className="font-bold text-slate-300 flex items-center gap-1.5">
              {activeTab === "search" ? (
                <Globe className="w-4 h-4 text-indigo-400" />
              ) : (
                <MapPin className="w-4 h-4 text-emerald-400" />
              )}
              Sahayak Grounded Insight
            </span>
            <span className="text-[10px] font-mono text-slate-500">{groundingSourceType}</span>
          </div>

          <p className="leading-relaxed text-slate-200 text-xs font-medium">{response}</p>

          {/* Render Grounding Source Links */}
          {sources.length > 0 && (
            <div className="pt-2 border-t border-slate-800/80">
              <span className="text-[11px] text-slate-400 font-bold block mb-1.5">
                Grounded Citations & Map Links:
              </span>
              <div className="flex flex-wrap gap-2">
                {sources.map((src, idx) => (
                  <a
                    key={idx}
                    href={src.uri}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-[11px] text-indigo-300 bg-indigo-950/60 border border-indigo-800/60 hover:bg-indigo-900/60 px-2.5 py-1 rounded-lg transition"
                  >
                    <ExternalLink className="w-3 h-3 text-indigo-400 shrink-0" />
                    <span className="truncate max-w-[200px]">{src.title}</span>
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
