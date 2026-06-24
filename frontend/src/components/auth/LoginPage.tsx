"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Eye, EyeOff, ArrowRight, Loader2, ShieldCheck,
  UserPlus, KeyRound, X, CheckCircle, Mail,
} from "lucide-react";
import axios from "axios";
import { useAuthStore, UserRole } from "@/lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const ROLE_REDIRECTS: Record<UserRole, string> = {
  super_admin: "/admin",
  admin: "/admin-ops",
  user: "/user-home",
};

// ── Forgot-Password modal ─────────────────────────────────────────────────────
function ForgotPasswordModal({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState<"email" | "sent">("email");
  const [fpEmail, setFpEmail] = useState("");
  const [fpBusy, setFpBusy] = useState(false);
  const [fpErr, setFpErr] = useState<string | null>(null);

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    setFpErr(null);
    if (!fpEmail.toLowerCase().endsWith("@amd.com")) {
      setFpErr("Enter your @amd.com email address.");
      return;
    }
    setFpBusy(true);
    // Simulated — wire to a real reset endpoint when available
    await new Promise((r) => setTimeout(r, 900));
    setFpBusy(false);
    setStep("sent");
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-surface border border-surface-2 rounded-2xl w-full max-w-sm shadow-2xl p-6 relative">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1 text-text-muted hover:text-text-primary transition-colors"
        >
          <X size={16} />
        </button>

        {step === "email" ? (
          <form onSubmit={send} className="space-y-5">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-cyan-400/10 border border-cyan-400/20 flex items-center justify-center flex-shrink-0">
                <KeyRound size={18} className="text-cyan-400" />
              </div>
              <div>
                <h3 className="font-bold text-text-primary">Forgot Password</h3>
                <p className="text-xs text-text-muted">We&apos;ll send a reset link to your AMD email</p>
              </div>
            </div>

            {fpErr && (
              <div className="text-xs text-red-400 bg-red-400/10 border border-red-400/30 rounded-lg px-3 py-2">
                {fpErr}
              </div>
            )}

            <div>
              <label className="text-xs text-text-muted mb-1 block">AMD Email</label>
              <input
                value={fpEmail}
                onChange={(e) => setFpEmail(e.target.value)}
                type="email"
                autoFocus
                placeholder="you@amd.com"
                className="w-full bg-background border border-surface-2 rounded-lg px-3 py-2.5 text-sm
                  focus:outline-none focus:border-cyan-500 focus:shadow-[0_0_0_3px_rgba(34,211,238,0.12)]"
              />
            </div>

            <button
              type="submit"
              disabled={fpBusy}
              className="w-full flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold text-white
                bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 disabled:opacity-50 transition-colors"
            >
              {fpBusy ? <Loader2 size={15} className="animate-spin" /> : <>Send Reset Link <ArrowRight size={15} /></>}
            </button>
          </form>
        ) : (
          <div className="space-y-4 text-center">
            <div className="w-14 h-14 rounded-full bg-green-400/10 border border-green-400/30 flex items-center justify-center mx-auto">
              <Mail size={24} className="text-green-400" />
            </div>
            <h3 className="font-bold text-text-primary">Check your inbox</h3>
            <p className="text-sm text-text-muted">
              If <span className="text-cyan-400">{fpEmail}</span> is registered, a password reset link has been sent.
              Check your AMD email inbox and spam folder.
            </p>
            <button
              onClick={onClose}
              className="w-full rounded-lg px-4 py-2.5 text-sm font-medium border border-surface-2
                hover:bg-surface-2 transition-colors"
            >
              Back to Sign In
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main LoginPage ────────────────────────────────────────────────────────────
export function LoginPage() {
  const [email, setEmail] = useState("");
  const [pwd, setPwd] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showForgot, setShowForgot] = useState(false);
  const router = useRouter();
  const setAuth = useAuthStore((s) => s.setAuth);

  const submit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setErr(null);
    if (!email.trim()) { setErr("Enter your AMD email address"); return; }
    if (!pwd) { setErr("Enter your password"); return; }

    setBusy(true);
    try {
      const res = await axios.post(`${API_BASE}/auth/login`, {
        email: email.trim().toLowerCase(),
        password: pwd,
      });
      const { access_token, refresh_token, user } = res.data;
      setAuth(user, access_token, refresh_token);
      router.replace(ROLE_REDIRECTS[user.role as UserRole] ?? "/");
    } catch (axiosErr: unknown) {
      const msg =
        (axiosErr as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Login failed. Check your credentials.";
      setErr(msg);
      setBusy(false);
    }
  };

  return (
    <>
      {showForgot && <ForgotPasswordModal onClose={() => setShowForgot(false)} />}

      <div className="min-h-screen grid grid-cols-1 lg:grid-cols-2 bg-background text-text-primary">
        {/* ── Brand panel ────────────────────────────────────────────── */}
        <div className="relative hidden lg:flex flex-col justify-between p-12 overflow-hidden">
          <div className="pointer-events-none absolute inset-0">
            <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full blur-3xl opacity-30 animate-pulse"
              style={{ background: "radial-gradient(circle, #22d3ee, transparent 70%)" }} />
            <div className="absolute bottom-0 right-0 w-[28rem] h-[28rem] rounded-full blur-3xl opacity-20 animate-pulse"
              style={{ background: "radial-gradient(circle, #ED1C24, transparent 70%)", animationDelay: "1s" }} />
            <div className="absolute inset-0 opacity-[0.07]"
              style={{ backgroundImage: "linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)", backgroundSize: "40px 40px" }} />
          </div>

          <div className="relative flex-1 flex flex-col items-center justify-center text-center">
            <div className="w-24 h-24 rounded-3xl flex items-center justify-center shadow-2xl shadow-cyan-500/20 mb-6"
              style={{ background: "linear-gradient(135deg, #f59e0b, #ED1C24)" }}>
              <span className="text-white font-bold text-6xl leading-none">☀</span>
            </div>
            <h1 className="text-6xl font-extrabold tracking-tight bg-clip-text text-transparent"
              style={{ backgroundImage: "linear-gradient(135deg, #fff, #67e8f9)" }}>
              Helios
            </h1>
            <p className="text-lg text-text-secondary mt-3 tracking-wide">AMD Server Fleet Observability</p>
            <p className="text-sm text-text-muted mt-6 max-w-md">
              Enterprise RBAC — Super Admin, Admin, and User roles with full audit logging
              for the AMD EPYC server estate.
            </p>
            <div className="mt-10 grid grid-cols-3 gap-3 text-center w-full max-w-sm">
              {[
                { role: "Super Admin", color: "text-red-400", desc: "Full control" },
                { role: "Admin", color: "text-amber-400", desc: "Operations" },
                { role: "User", color: "text-cyan-400", desc: "Resources" },
              ].map((r) => (
                <div key={r.role} className="bg-surface/50 border border-surface-2 rounded-xl p-3">
                  <p className={`font-semibold text-xs ${r.color}`}>{r.role}</p>
                  <p className="text-xs text-text-muted mt-1">{r.desc}</p>
                </div>
              ))}
            </div>
          </div>

          <p className="relative text-xs text-text-muted/60 text-center">Helios v1.0 · AMD · Datacenter Intelligence</p>
        </div>

        {/* ── Form panel ─────────────────────────────────────────────── */}
        <div className="flex items-center justify-center p-6 sm:p-12 border-l border-surface-2 bg-surface/30">
          <form onSubmit={submit} className="w-full max-w-sm space-y-6">
            {/* Mobile logo */}
            <div className="lg:hidden flex items-center gap-2 justify-center mb-2">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center"
                style={{ background: "linear-gradient(135deg, #f59e0b, #ED1C24)" }}>
                <span className="text-white font-bold">☀</span>
              </div>
              <span className="font-bold">Helios</span>
            </div>

            <div>
              <h2 className="text-2xl font-bold">Sign in</h2>
              <p className="text-sm text-text-muted mt-1">Access the Helios console with your AMD account</p>
            </div>

            {err && (
              <div className="text-sm text-red-400 bg-red-400/10 border border-red-400/30 rounded-lg px-3 py-2">
                {err}
              </div>
            )}

            <div className="space-y-3">
              <div>
                <label className="text-xs text-text-muted mb-1 block">AMD Email</label>
                <input
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoFocus
                  type="email"
                  placeholder="you@amd.com"
                  className="w-full bg-surface border border-surface-2 rounded-lg px-3 py-2.5 text-sm
                    focus:outline-none focus:border-cyan-500 focus:shadow-[0_0_0_3px_rgba(34,211,238,0.12)]"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs text-text-muted">Password</label>
                  <button
                    type="button"
                    onClick={() => setShowForgot(true)}
                    className="text-xs text-cyan-400 hover:text-cyan-300 hover:underline transition-colors"
                  >
                    Forgot password?
                  </button>
                </div>
                <div className="relative">
                  <input
                    type={show ? "text" : "password"}
                    value={pwd}
                    onChange={(e) => setPwd(e.target.value)}
                    placeholder="••••••••"
                    className="w-full bg-surface border border-surface-2 rounded-lg px-3 py-2.5 pr-10 text-sm
                      focus:outline-none focus:border-cyan-500 focus:shadow-[0_0_0_3px_rgba(34,211,238,0.12)]"
                  />
                  <button type="button" onClick={() => setShow((s) => !s)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary">
                    {show ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>
            </div>

            <button
              type="submit"
              disabled={busy}
              className="w-full flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold text-white
                bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 disabled:opacity-50 transition-colors"
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : <>Sign in <ArrowRight size={16} /></>}
            </button>

            <div className="flex items-center gap-3 text-xs text-text-muted">
              <div className="flex-1 border-t border-surface-2" /> or <div className="flex-1 border-t border-surface-2" />
            </div>

            <button
              type="button"
              onClick={() => setErr("AMD SSO integration coming soon. Use email + password.")}
              className="w-full flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium
                border border-surface-2 hover:bg-surface-2 transition-colors"
            >
              <ShieldCheck size={15} className="text-cyan-400" /> Sign in with AMD SSO
            </button>

            <div className="text-center">
              <Link href="/register" className="inline-flex items-center gap-1.5 text-sm text-cyan-400 hover:underline">
                <UserPlus size={14} /> Don&apos;t have an account? Register
              </Link>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}

