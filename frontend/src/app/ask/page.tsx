"use client";
import { useState, useRef, useEffect } from "react";
import { api } from "@/lib/api";
import { Sparkles, Send, User, Bot, AlertTriangle, Loader2, Wrench, Brain, Paperclip, Trash2 } from "lucide-react";
import { MiniMarkdown } from "@/components/MiniMarkdown";

// Extract server-like names from a pasted/CSV/Excel-exported list.
function parseServerNames(text: string): string[] {
  return Array.from(new Set(
    text.split(/[\s,;\n\r\t]+/)
      .map((t) => t.trim().replace(/^["']|["']$/g, ""))
      .filter((t) => /^[a-zA-Z0-9][\w.-]{2,}$/.test(t))
  ));
}

type Step = { kind: "thinking" | "tool" | "status"; text: string };
type Msg = { role: "user" | "assistant"; content: string; steps?: Step[]; tools?: string[]; route?: string; flags?: any; streaming?: boolean };

const SUGGESTIONS = [
  "How many critical servers are there?",
  "What are the top 5 hottest servers?",
  "Compare temperature of volcano-9a44 and volcano-9b70",
  "Why is titanite-35fc overheating and how do I prevent it?",
];

const HISTORY_KEY = "helios_chat_history";
const SESSION_KEY = "helios_chat_session";

export default function AskHeliosPage() {
  // Stable session id (persists so server-side short-term memory stays continuous)
  const [sessionId] = useState(() => {
    if (typeof window === "undefined") return "sess-ssr";
    let s = localStorage.getItem(SESSION_KEY);
    if (!s) { s = `sess-${Math.random().toString(36).slice(2, 10)}`; localStorage.setItem(SESSION_KEY, s); }
    return s;
  });
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Load saved chat history on mount (survives tab switches / reopen)
  useEffect(() => {
    try {
      const raw = localStorage.getItem(HISTORY_KEY);
      if (raw) {
        const saved: Msg[] = JSON.parse(raw);
        // never restore a dangling streaming flag
        setMsgs(saved.map((m) => ({ ...m, streaming: false })));
      }
    } catch { /* ignore */ }
    setLoaded(true);
  }, []);

  // Persist chat history whenever it changes (skip while streaming a partial)
  useEffect(() => {
    if (!loaded) return;
    if (busy) return;
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(msgs.slice(-100)));
    } catch { /* quota — ignore */ }
  }, [msgs, busy, loaded]);

  const clearChat = () => {
    setMsgs([]);
    try { localStorage.removeItem(HISTORY_KEY); } catch { /* ignore */ }
  };

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  // Auto-grow the textarea up to ~6 lines
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
  }, [input]);

  // Poll a BIOS batch job in the background and auto-post the result when it finishes —
  // no need for the user to ask again.
  const pollBatch = (batchId: string) => {
    const started = Date.now();
    const tick = async () => {
      try {
        const j = await fleetApi.biosBatchStatus(batchId);
        if (j.status === "completed" || j.status === "failed") {
          const s = j.summary || {};
          const rows = (j.servers || []).map((r: any) =>
            `| ${r.hostname} | ${r.bios_before ?? "—"} | ${r.bios_after ?? "—"} | ${r.flashed ? "✅ flashed" : (r.stage || "—")} |`).join("\n");
          const md = `## ✅ BIOS Batch Update Complete\n\n` +
            `**${s.flashed ?? 0}/${s.total ?? 0} servers flashed.**\n\n` +
            `| Server | BIOS Before | BIOS After | Result |\n|---|---|---|---|\n${rows}`;
          setMsgs((m) => [...m, { role: "assistant", content: md, streaming: false }]);
          return; // stop polling
        }
      } catch { /* keep trying */ }
      if (Date.now() - started < 45 * 60 * 1000) setTimeout(tick, 15000); // up to 45 min
    };
    setTimeout(tick, 15000);
  };

  const send = async (q: string) => {
    const text = q.trim();
    if (!text || busy) return;
    setInput("");
    setBusy(true);
    setMsgs((m) => [...m, { role: "user", content: text },
      { role: "assistant", content: "", steps: [], tools: [], streaming: true }]);

    const update = (fn: (m: Msg) => Msg) =>
      setMsgs((all) => { const c = [...all]; c[c.length - 1] = fn(c[c.length - 1]); return c; });

    try {
      const resp = await fetch(`${api.defaults.baseURL}/api/v1/ai/ask-stream`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text, session_id: sessionId }),
      });
      const reader = resp.body!.getReader();
      const dec = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() || "";
        for (const p of parts) {
          const line = p.trim();
          if (!line.startsWith("data:")) continue;
          let ev: any; try { ev = JSON.parse(line.slice(5).trim()); } catch { continue; }
          if (ev.type === "route") update((m) => ({ ...m, route: ev.route }));
          else if (ev.type === "status") update((m) => ({ ...m, steps: [...(m.steps || []), { kind: "status", text: ev.label }] }));
          else if (ev.type === "thinking") update((m) => ({ ...m, steps: [...(m.steps || []), { kind: "thinking", text: ev.text }] }));
          else if (ev.type === "tool") update((m) => ({ ...m, steps: [...(m.steps || []), { kind: "tool", text: ev.label }], tools: [...(m.tools || []), ev.tool] }));
          else if (ev.type === "answer") update((m) => ({ ...m, content: m.content + ev.delta }));
          else if (ev.type === "done") update((m) => ({ ...m, streaming: false, flags: ev.flags, route: ev.route || m.route }));
          else if (ev.type === "batch_started" && ev.batch_job_id) pollBatch(ev.batch_job_id);
          else if (ev.type === "error") update((m) => ({ ...m, content: "⚠ " + ev.message, streaming: false }));
        }
      }
    } catch {
      update((m) => ({ ...m, content: "Request failed — AI service may be down.", streaming: false }));
    } finally {
      setBusy(false);
      setMsgs((all) => { const c = [...all]; if (c.length) c[c.length - 1] = { ...c[c.length - 1], streaming: false }; return c; });
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-7rem)] animate-fade-in">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Sparkles size={18} className="text-cyan-400" /> Ask Helios
            <span className="text-[10px] uppercase tracking-wide bg-cyan-400/10 text-cyan-400 px-2 py-0.5 rounded-full">Claude-Opus-4.6 · live</span>
          </h1>
          <p className="text-sm text-text-muted">Reasons step-by-step over the live fleet — read-only, grounded in tool data.</p>
        </div>
        {msgs.length > 0 && (
          <button onClick={clearChat} title="Clear chat history"
            className="shrink-0 flex items-center gap-1 text-xs text-text-muted hover:text-red-400 border border-surface-2 rounded-lg px-2.5 py-1.5">
            <Trash2 size={13} /> Clear
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto space-y-4 pr-1">
        {msgs.length === 0 && (
          <div className="card">
            <p className="text-sm text-text-secondary mb-3">Try asking:</p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => send(s)} className="text-xs border border-surface-2 hover:border-cyan-500/50 hover:text-cyan-400 rounded-full px-3 py-1.5">{s}</button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`flex gap-3 ${m.role === "user" ? "justify-end" : ""}`}>
            {m.role === "assistant" && <div className="bg-cyan-400/10 rounded-lg p-2 h-8 w-8 flex items-center justify-center shrink-0"><Bot size={16} className="text-cyan-400" /></div>}
            <div className={`rounded-xl px-4 py-2.5 max-w-2xl ${m.role === "user" ? "bg-blue-600/20 border border-blue-600/30" : "bg-surface-2/60 border border-surface-2"}`}>
              {/* Minimal working indicator — internal tool/thinking steps are hidden. */}
              {m.role === "assistant" && m.streaming && !m.content && (
                <div className="flex items-center gap-2 text-xs text-cyan-400">
                  <Loader2 size={12} className="animate-spin" /> Helios is working…
                </div>
              )}
              {m.content && (
                m.role === "assistant"
                  ? <div className="text-sm">{m.streaming ? <p className="whitespace-pre-wrap">{m.content}<span className="inline-block w-1.5 h-4 bg-cyan-400 ml-0.5 animate-pulse align-middle" /></p> : <MiniMarkdown text={m.content} />}</div>
                  : <p className="text-sm whitespace-pre-wrap">{m.content}</p>
              )}
            </div>
            {m.role === "user" && <div className="bg-blue-400/10 rounded-lg p-2 h-8 w-8 flex items-center justify-center shrink-0"><User size={16} className="text-blue-400" /></div>}
          </div>
        ))}
        <div ref={endRef} />
      </div>

      {/* Composer */}
      <div className="mt-4">
        <div className={`relative flex items-end gap-2 bg-surface/80 backdrop-blur border rounded-2xl pl-4 pr-2 py-2 transition-all
          ${busy ? "border-surface-2 opacity-90" : "border-surface-2 focus-within:border-cyan-500/70 focus-within:shadow-[0_0_0_3px_rgba(34,211,238,0.12)]"}`}>
          <Sparkles size={16} className="text-cyan-400/70 shrink-0 mb-2" />
          {/* Attach a CSV/TXT/Excel-export of server names */}
          <input ref={fileRef} type="file" accept=".csv,.txt,.tsv,.list" className="hidden"
            onChange={async (e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              const text = await f.text();
              const names = parseServerNames(text);
              if (names.length) {
                setInput((prev) => (prev ? prev + "\n" : "") +
                  `Update BIOS on these ${names.length} servers: ${names.join(", ")}\nBIOS URL: `);
              }
              if (fileRef.current) fileRef.current.value = "";
            }} />
          <button type="button" title="Attach server list (CSV/TXT/Excel export)"
            onClick={() => fileRef.current?.click()} disabled={busy}
            className="shrink-0 mb-1.5 text-text-muted/70 hover:text-cyan-400 disabled:opacity-40">
            <Paperclip size={16} />
          </button>
          <textarea
            ref={taRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
            }}
            disabled={busy}
            rows={1}
            placeholder={busy ? "Helios is thinking…" : "Ask, or attach a server list to batch-update BIOS…"}
            className="flex-1 resize-none bg-transparent text-[15px] leading-6 tracking-tight text-text-primary
              placeholder:text-text-muted/60 focus:outline-none disabled:opacity-60 py-1.5 max-h-40 overflow-y-auto"
          />
          <button onClick={() => send(input)} disabled={busy || !input.trim()} title="Send (Enter)"
            className="shrink-0 mb-0.5 inline-flex items-center justify-center h-9 w-9 rounded-xl text-white
              bg-gradient-to-br from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500
              disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-lg shadow-cyan-500/20">
            {busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </div>
        <p className="text-[11px] text-text-muted/60 text-center mt-2">
          Helios AI reasons over live fleet data · read-only · <kbd className="px-1 py-0.5 rounded bg-surface-2 text-[10px]">Enter</kbd> to send · <kbd className="px-1 py-0.5 rounded bg-surface-2 text-[10px]">Shift+Enter</kbd> for newline
        </p>
      </div>
    </div>
  );
}
