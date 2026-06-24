"use client";
import { useState } from "react";
import { Download, Loader2, AlertCircle, CheckCircle2 } from "lucide-react";

interface ExportButtonProps {
  endpoint: string;
  filename?: string;
  params?: Record<string, string | number | boolean | undefined>;
  label?: string;
  className?: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function ExportButton({ endpoint, filename, params = {}, label = "Export CSV", className = "" }: ExportButtonProps) {
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");

  const download = async () => {
    setState("loading");
    setErrorMsg("");
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("helios_jwt") : null;
      if (!token) { setState("error"); setErrorMsg("Not logged in — please refresh the page"); return; }

      const qs = Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== null && v !== "")
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
        .join("&");

      const url = `${API_BASE}${endpoint}${qs ? "?" + qs : ""}`;
      const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });

      if (res.status === 401) { setState("error"); setErrorMsg("Session expired — please log in again"); return; }
      if (!res.ok) { setState("error"); setErrorMsg(`Server error: HTTP ${res.status}`); return; }

      const blob = await res.blob();
      if (blob.size === 0) { setState("error"); setErrorMsg("Empty response — no data to export"); return; }

      // Check if response is actually JSON error (not CSV)
      const text = await blob.text();
      if (text.startsWith("{") && text.includes("detail")) {
        const err = JSON.parse(text);
        setState("error");
        setErrorMsg(err.detail ?? "Export failed");
        return;
      }

      // Create download from text content
      const disposition = res.headers.get("Content-Disposition") ?? "";
      const match = disposition.match(/filename="?([^";\s]+)"?/);
      const name = match?.[1] ?? filename ?? `export_${endpoint.split("/").pop()}.csv`;

      const blobOut = new Blob([text], { type: "text/csv;charset=utf-8;" });
      const href = URL.createObjectURL(blobOut);
      const a = document.createElement("a");
      a.href = href; a.download = name;
      document.body.appendChild(a); a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(href);
      setState("done");
      setTimeout(() => setState("idle"), 3000);
    } catch (e: unknown) {
      setState("error");
      setErrorMsg(e instanceof Error ? e.message : "Download failed");
    }
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={download}
        disabled={state === "loading"}
        title={state === "error" ? errorMsg : `Download as CSV`}
        className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border rounded-lg transition-colors disabled:opacity-50 ${
          state === "error"
            ? "border-red-400/40 text-red-400 bg-red-400/10 hover:bg-red-400/20"
            : state === "done"
            ? "border-green-400/40 text-green-400 bg-green-400/10"
            : "border-surface-2 hover:bg-surface-2 hover:border-cyan-600/30 hover:text-cyan-400"
        } ${className}`}
      >
        {state === "loading" ? <Loader2 size={13} className="animate-spin" /> :
         state === "error"   ? <AlertCircle size={13} /> :
         state === "done"    ? <CheckCircle2 size={13} /> :
                               <Download size={13} />}
        {state === "done" ? "Downloaded!" : state === "error" ? "Failed" : label}
      </button>
      {state === "error" && errorMsg && (
        <p className="text-xs text-red-400 max-w-[200px] text-right">{errorMsg}</p>
      )}
    </div>
  );
}
