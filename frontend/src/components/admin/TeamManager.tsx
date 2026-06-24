"use client";
import { useState } from "react";
import { Plus, Pencil, Trash2, Loader2, X, Check } from "lucide-react";
import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Team {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
}

interface TeamManagerProps {
  teams: Team[];
  onRefresh: () => void;
}

export function TeamManager({ teams, onRefresh }: TeamManagerProps) {
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");

  const token = typeof window !== "undefined" ? localStorage.getItem("helios_jwt") : null;
  const headers = token ? { Authorization: `Bearer ${token}` } : {};

  const createTeam = async () => {
    if (!newName.trim()) return;
    setBusy(true);
    try {
      await axios.post(`${API_BASE}/admin/teams`, { name: newName.trim(), description: newDesc.trim() || null }, { headers });
      setNewName(""); setNewDesc(""); setShowCreate(false);
      onRefresh();
    } finally {
      setBusy(false);
    }
  };

  const updateTeam = async (id: string) => {
    if (!editName.trim()) return;
    setBusy(true);
    try {
      await axios.patch(`${API_BASE}/admin/teams/${id}`, { name: editName.trim() }, { headers });
      setEditId(null);
      onRefresh();
    } finally {
      setBusy(false);
    }
  };

  const toggleTeam = async (team: Team) => {
    setBusy(true);
    try {
      await axios.patch(`${API_BASE}/admin/teams/${team.id}`, { is_active: !team.is_active }, { headers });
      onRefresh();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-text-primary">Teams ({teams.length})</h3>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-cyan-600/20 border border-cyan-600/30 text-cyan-400 rounded-lg hover:bg-cyan-600/30 transition-colors"
        >
          <Plus size={12} /> New Team
        </button>
      </div>

      {showCreate && (
        <div className="bg-surface border border-surface-2 rounded-lg p-4 space-y-3">
          <p className="text-xs font-medium text-text-primary">Create New Team</p>
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Team name"
            className="w-full bg-background border border-surface-2 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
          />
          <input
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            placeholder="Description (optional)"
            className="w-full bg-background border border-surface-2 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
          />
          <div className="flex gap-2">
            <button
              onClick={createTeam}
              disabled={busy || !newName.trim()}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 disabled:opacity-50 transition-colors"
            >
              {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} Create
            </button>
            <button
              onClick={() => { setShowCreate(false); setNewName(""); setNewDesc(""); }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-surface-2 rounded-lg hover:bg-surface-2 transition-colors"
            >
              <X size={12} /> Cancel
            </button>
          </div>
        </div>
      )}

      <div className="space-y-2">
        {teams.map((team) => (
          <div
            key={team.id}
            className={`flex items-center justify-between p-3 rounded-lg border transition-colors ${
              team.is_active ? "bg-surface border-surface-2" : "bg-surface/30 border-surface-2/50 opacity-60"
            }`}
          >
            <div className="flex-1 min-w-0">
              {editId === team.id ? (
                <div className="flex items-center gap-2">
                  <input
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="flex-1 bg-background border border-cyan-500 rounded px-2 py-1 text-sm focus:outline-none"
                    autoFocus
                  />
                  <button onClick={() => updateTeam(team.id)} disabled={busy} className="text-green-400 hover:text-green-300">
                    <Check size={14} />
                  </button>
                  <button onClick={() => setEditId(null)} className="text-text-muted hover:text-text-primary">
                    <X size={14} />
                  </button>
                </div>
              ) : (
                <div>
                  <p className="text-sm font-medium text-text-primary">{team.name}</p>
                  {team.description && <p className="text-xs text-text-muted truncate">{team.description}</p>}
                </div>
              )}
            </div>

            {editId !== team.id && (
              <div className="flex items-center gap-1.5 ml-3 flex-shrink-0">
                <button
                  onClick={() => { setEditId(team.id); setEditName(team.name); }}
                  className="p-1 text-text-muted hover:text-text-primary transition-colors"
                >
                  <Pencil size={13} />
                </button>
                <button
                  onClick={() => toggleTeam(team)}
                  disabled={busy}
                  className={`p-1 transition-colors ${team.is_active ? "text-red-400 hover:text-red-300" : "text-green-400 hover:text-green-300"}`}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
