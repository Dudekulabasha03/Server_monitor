"use client";
import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight, Loader2, ArrowLeft, CheckCircle,
  Eye, EyeOff, X, Check,
} from "lucide-react";
import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Team { id: string; name: string; description: string; }

// Password rules — each must pass before submit is enabled
const PWD_RULES = [
  { key: "len",    label: "At least 8 characters",          test: (p: string) => p.length >= 8 },
  { key: "upper",  label: "One uppercase letter (A–Z)",      test: (p: string) => /[A-Z]/.test(p) },
  { key: "lower",  label: "One lowercase letter (a–z)",      test: (p: string) => /[a-z]/.test(p) },
  { key: "digit",  label: "One number (0–9)",                test: (p: string) => /\d/.test(p) },
  { key: "special",label: "One special character (!@#$…)",   test: (p: string) => /[^A-Za-z0-9]/.test(p) },
];

function strengthScore(p: string) {
  return PWD_RULES.filter((r) => r.test(p)).length;
}

const STRENGTH_META = [
  { label: "Too weak",  color: "bg-red-500",    text: "text-red-400"    },
  { label: "Weak",      color: "bg-orange-500",  text: "text-orange-400" },
  { label: "Fair",      color: "bg-yellow-400",  text: "text-yellow-400" },
  { label: "Good",      color: "bg-cyan-400",    text: "text-cyan-400"   },
  { label: "Strong",    color: "bg-green-400",   text: "text-green-400"  },
  { label: "Very strong",color: "bg-green-500",  text: "text-green-400"  },
];

// ── Password strength bar + rule list ───────────────────────────────────────
function PasswordStrength({ password }: { password: string }) {
  const score = strengthScore(password);
  const meta  = STRENGTH_META[score] ?? STRENGTH_META[0];

  if (!password) return null;

  return (
    <div className="mt-2 space-y-2">
      {/* Bar */}
      <div className="flex items-center gap-2">
        <div className="flex-1 flex gap-0.5">
          {STRENGTH_META.slice(0, 5).map((_, i) => (
            <div
              key={i}
              className={`h-1 flex-1 rounded-full transition-all duration-300 ${
                i < Math.ceil((score / PWD_RULES.length) * 5)
                  ? meta.color
                  : "bg-surface-2"
              }`}
            />
          ))}
        </div>
        <span className={`text-xs font-medium ${meta.text}`}>{meta.label}</span>
      </div>
      {/* Rule checklist */}
      <div className="grid grid-cols-1 gap-0.5">
        {PWD_RULES.map((rule) => {
          const ok = rule.test(password);
          return (
            <div key={rule.key} className="flex items-center gap-1.5">
              {ok
                ? <Check size={11} className="text-green-400 flex-shrink-0" />
                : <X    size={11} className="text-text-muted/50 flex-shrink-0" />}
              <span className={`text-xs ${ok ? "text-green-400" : "text-text-muted/60"}`}>
                {rule.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Confirm password feedback ────────────────────────────────────────────────
function ConfirmFeedback({ password, confirm }: { password: string; confirm: string }) {
  if (!confirm) return null;
  const match = password === confirm;
  return (
    <div className={`flex items-center gap-1.5 mt-1.5 text-xs ${match ? "text-green-400" : "text-red-400"}`}>
      {match
        ? <><Check size={11} /> Passwords match</>
        : <><X    size={11} /> Passwords do not match</>}
    </div>
  );
}

// ── Main RegisterPage ────────────────────────────────────────────────────────
export function RegisterPage() {
  const [fullName,        setFullName]        = useState("");
  const [email,           setEmail]           = useState("");
  const [teamId,          setTeamId]          = useState("");
  const [password,        setPassword]        = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPwd,         setShowPwd]         = useState(false);
  const [showConfirm,     setShowConfirm]     = useState(false);
  const [teams,           setTeams]           = useState<Team[]>([]);
  const [busy,            setBusy]            = useState(false);
  const [err,             setErr]             = useState<string | null>(null);
  const [success,         setSuccess]         = useState(false);
  const router = useRouter();

  useEffect(() => {
    axios.get(`${API_BASE}/auth/teams`).then((r) => setTeams(r.data)).catch(() => {});
  }, []);

  const allRulesPass = useMemo(() => PWD_RULES.every((r) => r.test(password)), [password]);
  const passwordsMatch = password === confirmPassword && confirmPassword.length > 0;
  const canSubmit = !busy && allRulesPass && passwordsMatch && fullName.trim() && email && teamId;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);

    if (!email.toLowerCase().endsWith("@amd.com")) {
      setErr("Only AMD email addresses (@amd.com) are accepted.");
      return;
    }
    if (!allRulesPass) {
      setErr("Password does not meet the strength requirements.");
      return;
    }
    if (!passwordsMatch) {
      setErr("Passwords do not match.");
      return;
    }
    if (!teamId) {
      setErr("Please select your team.");
      return;
    }

    setBusy(true);
    try {
      await axios.post(`${API_BASE}/auth/register`, {
        full_name: fullName.trim(),
        email: email.trim().toLowerCase(),
        team_id: teamId,
        password,
        confirm_password: confirmPassword,
      });
      setSuccess(true);
    } catch (axiosErr: unknown) {
      const msg =
        (axiosErr as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Registration failed. Please try again.";
      setErr(msg);
      setBusy(false);
    }
  };

  // ── Success screen ─────────────────────────────────────────────────────────
  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background text-text-primary p-6">
        <div className="max-w-md w-full text-center space-y-6">
          <div className="w-16 h-16 rounded-full bg-green-400/10 border border-green-400/30 flex items-center justify-center mx-auto">
            <CheckCircle size={32} className="text-green-400" />
          </div>
          <h2 className="text-2xl font-bold">Registration Submitted!</h2>
          <p className="text-text-muted text-sm">
            Your registration is <strong className="text-amber-400">pending admin approval</strong>.
            An administrator will review your account and activate it shortly.
            You will receive an email at your AMD address once approved.
          </p>
          <div className="bg-amber-400/10 border border-amber-400/30 rounded-xl px-4 py-3 text-sm text-amber-400">
            You cannot log in until your account is approved.
          </div>
          <button
            onClick={() => router.push("/login")}
            className="w-full flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold text-white
              bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 transition-colors"
          >
            Go to Sign In <ArrowRight size={16} />
          </button>
        </div>
      </div>
    );
  }

  // ── Form ───────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen grid grid-cols-1 lg:grid-cols-2 bg-background text-text-primary">
      {/* Brand panel */}
      <div className="relative hidden lg:flex flex-col justify-between p-12 overflow-hidden">
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full blur-3xl opacity-30 animate-pulse"
            style={{ background: "radial-gradient(circle, #22d3ee, transparent 70%)" }} />
          <div className="absolute bottom-0 right-0 w-[28rem] h-[28rem] rounded-full blur-3xl opacity-20 animate-pulse"
            style={{ background: "radial-gradient(circle, #ED1C24, transparent 70%)", animationDelay: "1s" }} />
        </div>
        <div className="relative flex-1 flex flex-col items-center justify-center text-center">
          <div className="w-24 h-24 rounded-3xl flex items-center justify-center shadow-2xl shadow-cyan-500/20 mb-6"
            style={{ background: "linear-gradient(135deg, #f59e0b, #ED1C24)" }}>
            <span className="text-white font-bold text-6xl leading-none">☀</span>
          </div>
          <h1 className="text-5xl font-extrabold tracking-tight bg-clip-text text-transparent"
            style={{ backgroundImage: "linear-gradient(135deg, #fff, #67e8f9)" }}>
            Join Helios
          </h1>
          <p className="text-lg text-text-secondary mt-3">AMD Fleet Observability Platform</p>
          <div className="mt-8 space-y-3 text-left w-full max-w-xs">
            {[
              "AMD @amd.com email required",
              "Strong password enforced",
              "Team assignment for resource scoping",
              "Role assigned by administrator",
              "Full audit trail of all actions",
            ].map((item) => (
              <div key={item} className="flex items-start gap-2 text-sm text-text-muted">
                <CheckCircle size={14} className="text-cyan-400 mt-0.5 flex-shrink-0" />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </div>
        <p className="relative text-xs text-text-muted/60 text-center">Helios v1.0 · AMD · Datacenter Intelligence</p>
      </div>

      {/* Form panel */}
      <div className="flex items-center justify-center p-6 sm:p-12 border-l border-surface-2 bg-surface/30 overflow-y-auto">
        <form onSubmit={submit} className="w-full max-w-sm space-y-4 py-4">
          <div>
            <Link href="/login" className="inline-flex items-center gap-1 text-sm text-text-muted hover:text-text-primary mb-4 transition-colors">
              <ArrowLeft size={14} /> Back to sign in
            </Link>
            <h2 className="text-2xl font-bold">Create Account</h2>
            <p className="text-sm text-text-muted mt-1">Register with your AMD credentials</p>
          </div>

          {err && (
            <div className="text-sm text-red-400 bg-red-400/10 border border-red-400/30 rounded-lg px-3 py-2">
              {err}
            </div>
          )}

          {/* Full Name */}
          <div>
            <label className="text-xs text-text-muted mb-1 block">Full Name <span className="text-red-400">*</span></label>
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
              autoFocus
              placeholder="Jane Doe"
              className="w-full bg-surface border border-surface-2 rounded-lg px-3 py-2.5 text-sm
                focus:outline-none focus:border-cyan-500 focus:shadow-[0_0_0_3px_rgba(34,211,238,0.12)]"
            />
          </div>

          {/* AMD Email */}
          <div>
            <label className="text-xs text-text-muted mb-1 block">AMD Email <span className="text-red-400">*</span></label>
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              type="email"
              placeholder="you@amd.com"
              className={`w-full bg-surface border rounded-lg px-3 py-2.5 text-sm focus:outline-none
                focus:shadow-[0_0_0_3px_rgba(34,211,238,0.12)] transition-colors ${
                  email && !email.toLowerCase().endsWith("@amd.com")
                    ? "border-red-500/60 focus:border-red-500"
                    : "border-surface-2 focus:border-cyan-500"
                }`}
            />
            {email && !email.toLowerCase().endsWith("@amd.com") && (
              <p className="text-xs text-red-400 mt-1 flex items-center gap-1">
                <X size={10} /> Only @amd.com addresses accepted
              </p>
            )}
          </div>

          {/* Team */}
          <div>
            <label className="text-xs text-text-muted mb-1 block">Team <span className="text-red-400">*</span></label>
            <select
              value={teamId}
              onChange={(e) => setTeamId(e.target.value)}
              required
              className="w-full bg-surface border border-surface-2 rounded-lg px-3 py-2.5 text-sm
                focus:outline-none focus:border-cyan-500"
            >
              <option value="">Select your team...</option>
              {teams.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>

          {/* Password */}
          <div>
            <label className="text-xs text-text-muted mb-1 block">Password <span className="text-red-400">*</span></label>
            <div className="relative">
              <input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                type={showPwd ? "text" : "password"}
                placeholder="Create a strong password"
                className="w-full bg-surface border border-surface-2 rounded-lg px-3 py-2.5 pr-10 text-sm
                  focus:outline-none focus:border-cyan-500 focus:shadow-[0_0_0_3px_rgba(34,211,238,0.12)]"
              />
              <button type="button" onClick={() => setShowPwd((s) => !s)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary">
                {showPwd ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
            <PasswordStrength password={password} />
          </div>

          {/* Confirm Password */}
          <div>
            <label className="text-xs text-text-muted mb-1 block">Confirm Password <span className="text-red-400">*</span></label>
            <div className="relative">
              <input
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                type={showConfirm ? "text" : "password"}
                placeholder="Re-enter your password"
                className={`w-full bg-surface border rounded-lg px-3 py-2.5 pr-10 text-sm focus:outline-none
                  focus:shadow-[0_0_0_3px_rgba(34,211,238,0.12)] transition-colors ${
                    confirmPassword
                      ? passwordsMatch
                        ? "border-green-500/60 focus:border-green-500"
                        : "border-red-500/60 focus:border-red-500"
                      : "border-surface-2 focus:border-cyan-500"
                  }`}
              />
              <button type="button" onClick={() => setShowConfirm((s) => !s)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary">
                {showConfirm ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
            <ConfirmFeedback password={password} confirm={confirmPassword} />
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={!canSubmit}
            className="w-full flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold text-white mt-2
              bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500
              disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {busy ? <Loader2 size={16} className="animate-spin" /> : <>Create Account <ArrowRight size={16} /></>}
          </button>

          <p className="text-xs text-text-muted text-center">
            Your access role will be assigned by an administrator after registration.
          </p>
        </form>
      </div>
    </div>
  );
}
