"use client";
import React from "react";
import { ChartBlock } from "@/components/ChartBlock";

/**
 * Dependency-free markdown renderer for AI answers.
 * Supports: # headings, **bold**, `code`, - / * bullet lists, 1. ordered lists,
 * and GitHub-style | tables |. Renders attractive styled elements (no raw * or |).
 */

function renderInline(text: string, keyBase: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  // split on **bold** and `code`
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  const parts = text.split(re);
  parts.forEach((p, i) => {
    if (!p) return;
    if (p.startsWith("**") && p.endsWith("**")) {
      nodes.push(<strong key={`${keyBase}-b${i}`} className="font-semibold text-text-primary">{p.slice(2, -2)}</strong>);
    } else if (p.startsWith("`") && p.endsWith("`")) {
      nodes.push(<code key={`${keyBase}-c${i}`} className="px-1.5 py-0.5 rounded bg-surface-2 text-cyan-300 text-[12px] font-mono">{p.slice(1, -1)}</code>);
    } else {
      nodes.push(<span key={`${keyBase}-t${i}`}>{p}</span>);
    }
  });
  return nodes;
}

function isTableSep(line: string): boolean {
  return /^\s*\|?[\s:|-]+\|?\s*$/.test(line) && line.includes("-");
}
function splitRow(line: string): string[] {
  let l = line.trim();
  if (l.startsWith("|")) l = l.slice(1);
  if (l.endsWith("|")) l = l.slice(0, -1);
  return l.split("|").map((c) => c.trim());
}

export function MiniMarkdown({ text }: { text: string }) {
  const lines = (text || "").split("\n");
  const out: React.ReactNode[] = [];
  let i = 0;
  let listBuf: { ordered: boolean; items: string[] } | null = null;

  const flushList = () => {
    if (!listBuf) return;
    const { ordered, items } = listBuf;
    out.push(
      ordered ? (
        <ol key={`ol-${out.length}`} className="list-decimal ml-5 space-y-1 my-1.5">
          {items.map((it, k) => <li key={k} className="text-sm leading-relaxed">{renderInline(it, `oli-${out.length}-${k}`)}</li>)}
        </ol>
      ) : (
        <ul key={`ul-${out.length}`} className="list-disc ml-5 space-y-1 my-1.5">
          {items.map((it, k) => <li key={k} className="text-sm leading-relaxed">{renderInline(it, `uli-${out.length}-${k}`)}</li>)}
        </ul>
      )
    );
    listBuf = null;
  };

  while (i < lines.length) {
    const line = lines[i];

    // Fenced block ```chart ... ``` -> render an ECharts chart from the JSON spec
    const fence = line.match(/^```(\w+)?\s*$/);
    if (fence) {
      flushList();
      const lang = (fence[1] || "").toLowerCase();
      const body: string[] = [];
      i++;
      while (i < lines.length && !/^```\s*$/.test(lines[i])) { body.push(lines[i]); i++; }
      i++; // consume closing fence
      const raw = body.join("\n").trim();
      if (lang === "chart" || lang === "graph") {
        try {
          const spec = JSON.parse(raw);
          out.push(<ChartBlock key={`chart-${out.length}`} spec={spec} />);
        } catch {
          out.push(<pre key={`pre-${out.length}`} className="text-xs bg-surface-2/60 rounded-lg p-3 overflow-x-auto my-2">{raw}</pre>);
        }
      } else {
        out.push(<pre key={`pre-${out.length}`} className="text-xs bg-surface-2/60 rounded-lg p-3 overflow-x-auto my-2 font-mono">{raw}</pre>);
      }
      continue;
    }

    // Table: header row + separator row + body rows
    if (line.includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      flushList();
      const header = splitRow(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].includes("|") && lines[i].trim() !== "") {
        rows.push(splitRow(lines[i]));
        i++;
      }
      out.push(
        <div key={`tbl-${out.length}`} className="my-2 overflow-x-auto rounded-lg border border-surface-2">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-2/60">
                {header.map((h, k) => (
                  <th key={k} className="text-left px-3 py-2 text-xs font-semibold text-text-secondary uppercase tracking-wide whitespace-nowrap">
                    {renderInline(h, `th-${out.length}-${k}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, rk) => (
                <tr key={rk} className="border-t border-surface-2 hover:bg-surface-2/30">
                  {r.map((c, ck) => (
                    <td key={ck} className="px-3 py-1.5 align-top">{renderInline(c, `td-${out.length}-${rk}-${ck}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    // Headings
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      flushList();
      const lvl = h[1].length;
      const cls = lvl <= 1 ? "text-base font-bold mt-2 mb-1"
        : lvl === 2 ? "text-sm font-bold mt-2 mb-1"
        : "text-sm font-semibold mt-1.5 mb-0.5 text-text-secondary";
      out.push(<div key={`h-${out.length}`} className={cls}>{renderInline(h[2], `h-${out.length}`)}</div>);
      i++;
      continue;
    }

    // List items
    const ul = line.match(/^\s*[-*]\s+(.*)$/);
    const ol = line.match(/^\s*\d+\.\s+(.*)$/);
    if (ul) {
      if (!listBuf || listBuf.ordered) { flushList(); listBuf = { ordered: false, items: [] }; }
      listBuf.items.push(ul[1]);
      i++;
      continue;
    }
    if (ol) {
      if (!listBuf || !listBuf.ordered) { flushList(); listBuf = { ordered: true, items: [] }; }
      listBuf.items.push(ol[1]);
      i++;
      continue;
    }

    // Blank line
    if (line.trim() === "") {
      flushList();
      i++;
      continue;
    }

    // Paragraph
    flushList();
    out.push(<p key={`p-${out.length}`} className="text-sm leading-relaxed my-1">{renderInline(line, `p-${out.length}`)}</p>);
    i++;
  }
  flushList();
  return <div className="space-y-0.5">{out}</div>;
}
