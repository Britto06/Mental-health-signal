import React, { useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

// ---- Backend hookup ----------------------------------------------------
// Leave this empty to run the local demo model (works standalone, no server).
// Once your FastAPI backend is deployed (e.g. on Render), put its URL here,
// e.g. "https://mental-health-signal-api.onrender.com" — the site will then
// call POST {API_BASE_URL}/predict instead of using the local formula.
const API_BASE_URL = "";

const STRESS_LEVELS = ["Low", "Medium", "High", "Very High"];
const STRESS_WEIGHT = { Low: 0, Medium: 1, High: 2.5, "Very High": 4.2 };

const BANDS = [
  { max: 2.5, label: "steady", color: "#5C9A83", desc: "Your rhythm looks steady, with healthy room to spare." },
  { max: 5, label: "balanced", color: "#C9A94B", desc: "Your rhythm looks fairly steady, with some room to recover and reset." },
  { max: 7.5, label: "elevated", color: "#D9863F", desc: "A few habits are pulling your signal up — small changes should help." },
  { max: 10.01, label: "strained", color: "#C8593F", desc: "Several factors are stacking up right now — worth addressing soon." },
];
const bandFor = (score) => BANDS.find((b) => score <= b.max);

// Younger users are typically more affected by heavy screen/phone habits;
// that sensitivity tapers with age. Only scales the *digital* factors.
function ageModifier(age) {
  return Math.max(0.8, Math.min(1.3, 1.3 - (age - 15) * 0.015));
}

function computeScore(f) {
  const factors = [];
  const push = (label, value) => { if (value > 0.05) factors.push({ label, value }); };
  let score = 0;
  const ageMod = ageModifier(f.age);

  const sleepExtra = Math.max(0, 7 - f.sleep) * 0.5 + Math.max(0, f.sleep - 9) * 0.3;
  push("Short sleep", sleepExtra); score += sleepExtra;

  const screenExtra = Math.max(0, f.screenTime - 4) * 0.35 * ageMod;
  push("High screen time", screenExtra); score += screenExtra;

  const unlockExtra = Math.max(0, f.phoneUnlocks - 60) * 0.015 * ageMod;
  push("Frequent phone unlocks", unlockExtra); score += unlockExtra;

  let studyExtra = 0, studyLabel = "";
  if (f.studyHours < 1.5) { studyExtra = (1.5 - f.studyHours) * 0.4; studyLabel = "Low study time"; }
  if (f.studyHours > 7) { studyExtra = (f.studyHours - 7) * 0.3; studyLabel = "Long study hours"; }
  push(studyLabel, studyExtra); score += studyExtra;

  const activityExtra = Math.max(0, 0.5 - f.activity) * 1.0;
  push("Low physical activity", activityExtra); score += activityExtra;

  const purposeExtra = f.purpose === "Entertainment" && f.screenTime > 5 ? 0.4 * ageMod : 0;
  push("Entertainment-heavy usage", purposeExtra); score += purposeExtra;

  const stressWeight = STRESS_WEIGHT[f.stress];
  push(`${f.stress} stress`, stressWeight); score += stressWeight;

  score = Math.max(0, Math.min(10, score));
  factors.sort((a, b) => b.value - a.value);
  return { score: Math.round(score * 100) / 100, factors: factors.slice(0, 3) };
}

function tipFor(factors) {
  if (!factors.length) return "Your inputs aren't pulling the score in any strong direction right now.";
  const top = factors[0].label;
  if (top.includes("sleep")) return "Short sleep is the biggest pull here — even 45 extra minutes a night tends to move this a lot.";
  if (top.includes("screen")) return "Screen time is the biggest factor — try one no-phone hour before bed and re-run this.";
  if (top.includes("unlocks")) return "You're unlocking your phone a lot — try turning off non-essential notifications for a day.";
  if (top.includes("stress")) return "Stress level is driving most of this score — worth flagging to a mentor or counsellor if it's been sustained.";
  if (top.includes("activity")) return "Low activity is a factor — a 20-minute walk most days tends to help this kind of score.";
  if (top.includes("study")) return "Your study hours are pulling this — balance matters more than raw hours.";
  if (top.includes("Entertainment")) return "A lot of your screen time is entertainment — try swapping 30 min of it for something active.";
  return "Small habit changes here would shift the score.";
}

// Per-factor detail, shown when a factor row is expanded (feature 6).
function factorAdvice(label) {
  if (label.includes("sleep")) return "Every hour under 7 adds about 0.5 pts. Try shifting bedtime 30 min earlier for a few nights and re-run this.";
  if (label.includes("screen")) return "Each hour above 4/day adds roughly 0.35 pts (more if you're younger). One no-phone hour before bed is the fastest lever.";
  if (label.includes("unlocks")) return "Every unlock past 60/day adds a small amount. Turning off non-essential notifications usually cuts this fast.";
  if (label.includes("stress")) return "This is the single biggest driver in the model. If it's been sustained, it's worth talking to a mentor or counsellor.";
  if (label.includes("activity")) return "Getting to at least 30 min/day of movement removes this factor entirely.";
  if (label.includes("Low study")) return "Very low study time can itself be a stress signal — worth checking what's getting in the way.";
  if (label.includes("Long study")) return "Long hours without breaks compounds strain — try the Pomodoro method (25 min on, 5 off).";
  if (label.includes("Entertainment")) return "Swapping some entertainment screen time for something offline tends to help both this and the screen-time factor.";
  return "Small, consistent changes here shift the score.";
}

const DEFAULTS = {
  age: 20, gender: "Male", academicLevel: "Undergraduate", platform: "Instagram",
  purpose: "Entertainment", screenTime: 5, phoneUnlocks: 85, studyHours: 3,
  activity: 1, sleep: 7, stress: "Medium",
};

function useCountUp(target, active) {
  const [val, setVal] = React.useState(0);
  React.useEffect(() => {
    if (!active) return;
    let raf;
    const start = performance.now();
    const duration = 900;
    const tick = (now) => {
      const p = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setVal(target * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, active]);
  return active ? val : 0;
}

function Gauge({ pct, active }) {
  const cx = 100, cy = 100, r = 78;
  const angle = 180 - pct * 180;
  const rad = (angle * Math.PI) / 180;
  const dotX = cx + r * Math.cos(rad);
  const dotY = cy - r * Math.sin(rad);
  const arcPath = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;
  const ticks = [0, 45, 90, 135, 180];
  return (
    <svg viewBox="0 0 200 115" className="w-full max-w-[220px]">
      <defs>
        <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#C8593F" />
          <stop offset="50%" stopColor="#C9A94B" />
          <stop offset="100%" stopColor="#5C9A83" />
        </linearGradient>
      </defs>
      {ticks.map((t) => {
        const a = (t * Math.PI) / 180;
        const x1 = cx + (r + 6) * Math.cos(a), y1 = cy - (r + 6) * Math.sin(a);
        const x2 = cx + (r + 13) * Math.cos(a), y2 = cy - (r + 13) * Math.sin(a);
        return <line key={t} x1={x1} y1={y1} x2={x2} y2={y2} stroke="rgba(255,255,255,0.25)" strokeWidth="2" strokeLinecap="round" />;
      })}
      <path d={arcPath} fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="10" strokeLinecap="round" />
      {active && <path d={arcPath} fill="none" stroke="url(#gaugeGrad)" strokeWidth="10" strokeLinecap="round" className="gauge-arc-in" />}
      {active && <circle cx={dotX} cy={dotY} r="7" fill="#FFFFFF" className="gauge-dot" />}
    </svg>
  );
}

function Spinner() {
  return (
    <svg viewBox="0 0 120 120" className="w-28 h-28 spin-slow">
      <circle cx="60" cy="60" r="44" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="1.5" />
      <circle cx="60" cy="60" r="30" fill="none" stroke="rgba(255,255,255,0.25)" strokeWidth="1.5" />
      <circle cx="60" cy="60" r="30" fill="none" stroke="#7FAE9D" strokeWidth="3" strokeLinecap="round" strokeDasharray="40 148" />
    </svg>
  );
}

// Small "?" tooltip used next to fields (feature 2).
function Info({ text }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="info-wrap">
      <button type="button" className="info-btn" onClick={() => setOpen((o) => !o)} onBlur={() => setOpen(false)}>?</button>
      {open && <span className="info-bubble">{text}</span>}
    </span>
  );
}

export default function MentalHealthSignal() {
  const [form, setForm] = useState(DEFAULTS);
  const [status, setStatus] = useState("idle"); // idle | loading | success | error
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [runKey, setRunKey] = useState(0);
  const [usingLiveModel, setUsingLiveModel] = useState(false);
  const [lastReadAt, setLastReadAt] = useState(null);
  const [expandedFactor, setExpandedFactor] = useState(null);
  const [studentId, setStudentId] = useState("STU001");
  const [reminderEmail, setReminderEmail] = useState("");
  const [reminderChannel, setReminderChannel] = useState("email"); // "email" | "whatsapp"
  const [reminderInterval, setReminderInterval] = useState(7); // 1 | 2 | 7
  const [reminderSaved, setReminderSaved] = useState(false);
  const [reminderError, setReminderError] = useState(false);
  const [mongoHistory, setMongoHistory] = useState([]);
  const [goalTarget, setGoalTarget] = useState(null);
  const [goalInput, setGoalInput] = useState("5");

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const setNumField = (key) => (val) => setForm((f) => ({ ...f, [key]: val }));

  const loadHistory = (sid) => {
    if (!API_BASE_URL || !sid) return;
    fetch(`${API_BASE_URL}/predictions/history/${encodeURIComponent(sid)}`)
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => {
        if (Array.isArray(data)) setMongoHistory(data);
      })
      .catch(() => {});
  };

  const finishSuccess = (r, live) => {
    setResult(r);
    setUsingLiveModel(live);
    setHistory((h) => [...h, { run: h.length + 1, score: r.score }]);
    setLastReadAt(new Date());
    setStatus("success");
    setRunKey((k) => k + 1);
    if (live && studentId) {
      loadHistory(studentId);
    }
  };

  const runRead = () => {
    setStatus("loading");
    setExpandedFactor(null);

    if (!API_BASE_URL) {
      // Demo mode: no backend connected yet, use the local rule-based model.
      setTimeout(() => finishSuccess(computeScore(form), false), 700);
      return;
    }

    // Live mode: call real FastAPI + joblib model.
    const url = `${API_BASE_URL}/predict?student_id=${encodeURIComponent(studentId || "anonymous")}`;
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...form, studentId: studentId || undefined }),
    })
      .then((res) => { if (!res.ok) throw new Error("bad response"); return res.json(); })
      .then((data) => finishSuccess({ score: data.score, factors: data.factors || [] }, true))
      .catch(() => setStatus("error"));
  };

  const saveReminder = () => {
    setReminderError(false);
    if (!API_BASE_URL) {
      // Demo mode: nothing to call — this just previews the flow.
      setReminderSaved(true);
      return;
    }
    const payload = {
      student_id: studentId.trim() || reminderEmail.trim(),
      email: reminderChannel === "email" ? reminderEmail.trim() : undefined,
      phone: reminderChannel === "whatsapp" ? reminderEmail.trim() : undefined,
      reminder_channel: reminderChannel,
      reminder_interval_days: Number(reminderInterval),
      reminders_enabled: true,
    };
    fetch(`${API_BASE_URL}/reminders/preferences`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((res) => { if (!res.ok) throw new Error("bad response"); return res.json(); })
      .then(() => setReminderSaved(true))
      .catch(() => setReminderError(true));
  };

  const saveGoal = () => {
    const v = Number(goalInput);
    if (!isNaN(v) && v >= 0 && v <= 10) setGoalTarget(v);
  };

  const exportCSV = () => {
    const rows = ["run,score", ...history.map((h) => `${h.run},${h.score}`)].join("\n");
    const blob = new Blob([rows], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "mental_health_signal_history.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const runAnother = () => { setStatus("idle"); setResult(null); };
  const tryAgain = () => setStatus("idle");
  const resetAll = () => { setForm(DEFAULTS); setStatus("idle"); setResult(null); setHistory([]); setExpandedFactor(null); };

  const displayScore = useCountUp(result ? result.score : 0, status === "success");
  const maxFactor = result && result.factors.length ? Math.max(...result.factors.map((f) => f.value)) : 1;
  const band = result ? bandFor(result.score) : null;

  return (
    <div className="page min-h-screen w-full p-6 md:p-10">
      <div className="max-w-5xl mx-auto mb-8 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <p className="eyebrow text-[13px] mb-2">Student wellness analytics</p>
          <h1 className="heading text-4xl md:text-5xl font-medium">
            Mental Health <span className="italic">Signal</span>
          </h1>
          <p className="muted mt-3 max-w-md text-[15px] leading-relaxed">
            A quick read on how habits, screen time, and stress are trending — modeled from your daily rhythm, not a diagnosis.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {history.length > 1 && (
            <button onClick={exportCSV} className="btn-ghost text-xs rounded-lg px-3 py-2">Export CSV ↓</button>
          )}
          <button onClick={resetAll} className="btn-ghost text-xs rounded-lg px-3 py-2">Reset form</button>
        </div>
      </div>

      <div className="max-w-5xl mx-auto grid md:grid-cols-[1fr_360px] gap-6">
        {/* FORM */}
        <div className="card rounded-2xl p-7">
          <Section title="Profile">
            <Row>
              <NumberField label="Age" hint="10–100" value={form.age} onChange={setNumField("age")} min={10} max={100}
                info="Used to scale how much screen-time and phone-check habits count — younger users tend to be more sensitive to heavy usage." />
              <Field label="Gender">
                <select value={form.gender} onChange={set("gender")} className="input">
                  <option>Male</option><option>Female</option><option>Other</option>
                </select>
              </Field>
            </Row>
          </Section>

          <Section title="Academic & digital habits">
            <Row>
              <Field label="Academic level">
                <select value={form.academicLevel} onChange={set("academicLevel")} className="input">
                  <option>Undergraduate</option><option>Postgraduate</option><option>High school</option>
                </select>
              </Field>
              <Field label="Most-used platform">
                <select value={form.platform} onChange={set("platform")} className="input">
                  <option>Instagram</option><option>YouTube</option><option>WhatsApp</option><option>X</option>
                </select>
              </Field>
            </Row>
            <Row>
              <Field label="Primary purpose" hint="Why you mainly use it">
                <select value={form.purpose} onChange={set("purpose")} className="input">
                  <option>Entertainment</option>
                  <option>Education</option>
                  <option>Social connection</option>
                  <option>Work</option>
                </select>
              </Field>
              <NumberField label="Avg. daily screen time" unit="hrs" value={form.screenTime} onChange={setNumField("screenTime")} min={0} max={16} step={0.5}
                info="Total hours per day across all apps combined, not just one platform." />
            </Row>
            <Row>
              <NumberField label="Daily phone unlocks" value={form.phoneUnlocks} onChange={setNumField("phoneUnlocks")} min={0} max={300} step={5}
                info="How many times you check/unlock your phone in a day. Most people average around 50–60." />
            </Row>
          </Section>

          <Section title="Lifestyle & stress" noBorder>
            <Row>
              <NumberField label="Study hours / day" unit="hrs" value={form.studyHours} onChange={setNumField("studyHours")} min={0} max={16} step={0.5}
                info="Focused study time — not just hours with a book open nearby." />
              <NumberField label="Physical activity / day" unit="hrs" value={form.activity} onChange={setNumField("activity")} min={0} max={8} step={0.5}
                info="Any movement that raises your heart rate a bit — walking, sports, gym. 30 min/day is a common baseline." />
              <NumberField label="Sleep / night" unit="hrs" value={form.sleep} onChange={setNumField("sleep")} min={0} max={14} step={0.5}
                info="Hours actually asleep, not time spent lying in bed." />
            </Row>
            <div className="mt-4">
              <label className="label text-[13px] flex items-center mb-2">
                Perceived stress level
                <Info text="How stressed you personally feel lately — not a clinical measurement." />
              </label>
              <div className="flex gap-2 flex-wrap">
                {STRESS_LEVELS.map((s) => {
                  const selected = form.stress === s;
                  return (
                    <button key={s} type="button" onClick={() => setForm((f) => ({ ...f, stress: s }))}
                      className={`stress-btn ${selected ? "stress-btn-selected" : ""}`}>
                      {selected && <span className="stress-check">✓</span>}
                      {s}
                    </button>
                  );
                })}
              </div>
            </div>
          </Section>

          <button onClick={runRead} disabled={status === "loading"} className="btn-primary mt-2 w-full rounded-xl text-[15px] font-medium py-3.5 flex items-center justify-center gap-2">
            {status === "loading" ? "Reading..." : "Read my signal"}
            {status !== "loading" && <span aria-hidden="true" className="btn-arrow">→</span>}
          </button>
        </div>

        {/* RESULT */}
        <div className="card-dark rounded-2xl p-7 flex flex-col items-center justify-center min-h-[520px]">
          {status === "idle" && (
            <div className="flex flex-col items-center text-center fade-in">
              <Gauge pct={0} active={false} />
              <p className="italic text-lg mt-4 mb-2 serif">Your score will appear here</p>
              <p className="text-sm dim max-w-[220px]">Fill in the form and submit to generate a predicted mental health score from 0–10.</p>
            </div>
          )}

          {status === "loading" && (
            <div className="flex flex-col items-center text-center fade-in">
              <Spinner />
              <p className="italic text-lg mt-4 mb-1 serif">Reading the signal...</p>
              <p className="text-sm dim">{API_BASE_URL ? "Calling the model API." : "Running your habits through the local model."}</p>
            </div>
          )}

          {status === "error" && (
            <div className="flex flex-col items-center text-center fade-in">
              <div className="error-icon">!</div>
              <p className="text-sm dim3 mt-4 mb-4 max-w-[220px]">Couldn't reach the model API. Your inputs are still saved — just try again.</p>
              <button onClick={tryAgain} className="btn-white rounded-lg px-5 py-2.5 text-sm font-medium">Try again</button>
            </div>
          )}

          {status === "success" && result && (
            <div key={runKey} className="w-full flex flex-col items-center pop-in">
              <Gauge pct={displayScore / 10} active={true} />
              <span className="model-badge">{usingLiveModel ? "● Live model" : "● Local demo model"}</span>
              <div className="flex items-baseline gap-1 mt-2">
                <span className="serif text-4xl">{displayScore.toFixed(2)}</span>
                <span className="text-sm dim">/10</span>
              </div>
              <p className="italic text-lg mt-2 mb-1 serif">Signal: {band.label}</p>
              <p className="text-sm dim text-center max-w-[240px] mb-2">{band.desc}</p>
              {goalTarget != null && (
                <p className="text-xs mb-3" style={{ color: result.score <= goalTarget ? "#7FAE9D" : "#E08A6B" }}>
                  {result.score <= goalTarget
                    ? `🎉 Within your goal of under ${goalTarget}`
                    : `${(result.score - goalTarget).toFixed(2)} above your goal of under ${goalTarget}`}
                </p>
              )}

              <button onClick={runAnother} className="btn-white rounded-lg px-5 py-2.5 text-sm font-medium mb-6">Run another read</button>

              <div className="w-full space-y-3 mb-4" style={{ borderTop: "1px solid rgba(255,255,255,0.1)", paddingTop: 16 }}>
                <p className="text-xs dim2 mb-1">Why this score — tap a factor for detail</p>
                {result.factors.length === 0 && <p className="text-xs dim2">No single factor stands out — inputs look balanced.</p>}
                {result.factors.map((f, i) => {
                  const isOpen = expandedFactor === f.label;
                  return (
                    <div key={f.label}>
                      <button type="button" className="factor-row" onClick={() => setExpandedFactor(isOpen ? null : f.label)}>
                        <span className="flex justify-between w-full text-xs dim3 mb-1">
                          <span>{f.label}</span>
                          <span className="factor-chevron">{isOpen ? "−" : "+"}</span>
                        </span>
                      </button>
                      <div className="h-1.5 rounded-full overflow-hidden bar-track">
                        <div className="h-full bar-fill" style={{ width: `${(f.value / maxFactor) * 100}%`, background: band.color, transitionDelay: `${i * 80}ms` }} />
                      </div>
                      {isOpen && (
                        <div className="factor-detail">
                          <p className="mb-1">Contribution: <strong>+{f.value.toFixed(2)} pts</strong> of your {result.score.toFixed(2)} total</p>
                          <p>{factorAdvice(f.label)}</p>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              <p className="text-xs dim3 leading-relaxed w-full" style={{ borderTop: "1px solid rgba(255,255,255,0.1)", paddingTop: 12 }}>
                {tipFor(result.factors)}
              </p>

              {history.length > 1 && (
                <div className="w-full mt-5 pt-4" style={{ borderTop: "1px solid rgba(255,255,255,0.1)" }}>
                  <p className="text-xs dim2 mb-2">This session's trend</p>
                  <ResponsiveContainer width="100%" height={80}>
                    <LineChart data={history}>
                      <XAxis dataKey="run" hide />
                      <YAxis domain={[0, 10]} hide />
                      <Tooltip contentStyle={{ background: "#1F3D34", border: "none", fontSize: 12 }} />
                      <Line type="monotone" dataKey="score" stroke="#7FAE9D" strokeWidth={2} dot={{ r: 3, fill: "#7FAE9D" }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Weekly check-in reminder (feature 7) + Goal tracking (feature 5) */}
      <div className="max-w-5xl mx-auto mt-6 grid md:grid-cols-2 gap-4">
        <div className="card rounded-2xl p-6">
          <h3 className="section-title text-[15px] font-medium mb-1">Check-in reminder & frequency</h3>
          <p className="muted text-sm mb-3">
            {lastReadAt
              ? `Last read: just now. Next suggested check-in based on your ${reminderInterval === 1 ? "daily" : reminderInterval === 2 ? "2-day" : "weekly"} preference.`
              : "Choose how often you would like to complete your check-in."}
          </p>

          {/* Student ID input */}
          <div className="mb-3">
            <label className="label text-[12px] block mb-1">Student ID (tracks your history)</label>
            <input
              type="text"
              placeholder="e.g. STU001"
              value={studentId}
              onChange={(e) => {
                setStudentId(e.target.value);
                setReminderSaved(false);
                loadHistory(e.target.value);
              }}
              className="input"
              style={{ maxWidth: 220 }}
            />
          </div>

          {/* Reminder frequency */}
          <label className="label text-[12px] block mb-1">Reminder frequency</label>
          <div className="flex gap-2 mb-3 flex-wrap">
            <button
              type="button"
              onClick={() => { setReminderInterval(1); setReminderSaved(false); }}
              className={`channel-btn ${reminderInterval === 1 ? "channel-btn-selected" : ""}`}>
              Daily (1 day)
            </button>
            <button
              type="button"
              onClick={() => { setReminderInterval(2); setReminderSaved(false); }}
              className={`channel-btn ${reminderInterval === 2 ? "channel-btn-selected" : ""}`}>
              Every 2 days
            </button>
            <button
              type="button"
              onClick={() => { setReminderInterval(7); setReminderSaved(false); }}
              className={`channel-btn ${reminderInterval === 7 ? "channel-btn-selected" : ""}`}>
              Weekly (7 days)
            </button>
          </div>

          {/* Notification channel */}
          <label className="label text-[12px] block mb-1">Notification channel</label>
          <div className="flex gap-2 mb-3">
            <button type="button" onClick={() => { setReminderChannel("email"); setReminderSaved(false); }}
              className={`channel-btn ${reminderChannel === "email" ? "channel-btn-selected" : ""}`}>Email</button>
            <button type="button" onClick={() => { setReminderChannel("whatsapp"); setReminderSaved(false); }}
              className={`channel-btn ${reminderChannel === "whatsapp" ? "channel-btn-selected" : ""}`}>WhatsApp</button>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {reminderChannel === "email" ? (
              <input type="email" placeholder="you@college.edu" value={reminderEmail}
                onChange={(e) => { setReminderEmail(e.target.value); setReminderSaved(false); }}
                className="input" style={{ flex: 1, minWidth: 160 }} />
            ) : (
              <input type="tel" placeholder="+91 98765 43210" value={reminderEmail}
                onChange={(e) => { setReminderEmail(e.target.value); setReminderSaved(false); }}
                className="input" style={{ flex: 1, minWidth: 160 }} />
            )}
            <button onClick={saveReminder} disabled={!reminderEmail}
              className="btn-primary rounded-lg px-4 py-2.5 text-sm font-medium" style={{ opacity: reminderEmail ? 1 : 0.5 }}>
              {reminderSaved ? "Saved ✓" : "Save preference"}
            </button>
          </div>
          {reminderSaved && (
            <p className="text-xs mt-2 muted">
              {API_BASE_URL
                ? `Saved to MongoDB! Reminders set for ${reminderInterval === 1 ? "Daily" : reminderInterval === 2 ? "Every 2 days" : "Weekly"} via ${reminderChannel}.`
                : "Demo mode: preference saved locally. Set API_BASE_URL to your deployed api.py to sync with MongoDB."}
            </p>
          )}
          {reminderError && (
            <p className="text-xs mt-2" style={{ color: "#C8593F" }}>
              Couldn't reach the backend to save that — check that the API is running.
            </p>
          )}

          {/* MongoDB Historical Log display if available */}
          {mongoHistory.length > 0 && (
            <div className="mt-4 pt-3" style={{ borderTop: "1px solid #EEF1EC" }}>
              <p className="text-xs font-medium section-title mb-2">Previous Check-Ins (MongoDB History)</p>
              <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
                {mongoHistory.slice(-5).reverse().map((item, idx) => (
                  <div key={idx} className="flex justify-between text-xs py-1 px-2 rounded bg-stone-50">
                    <span className="muted">{item.date}</span>
                    <span className="font-medium text-[#1F3D34]">Score: {item.mental_health_score.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="card rounded-2xl p-6">
          <h3 className="section-title text-[15px] font-medium mb-1">Your goal</h3>
          <p className="muted text-sm mb-3">
            {goalTarget != null
              ? `Current goal: stay under ${goalTarget}.`
              : "Set a target score to track progress toward, instead of just watching the raw number."}
          </p>
          <div className="flex items-center gap-2">
            <span className="text-sm muted">Stay under</span>
            <input type="number" min={0} max={10} step={0.5} value={goalInput}
              onChange={(e) => setGoalInput(e.target.value)}
              className="input" style={{ width: 70, textAlign: "center" }} />
            <button onClick={saveGoal} className="btn-primary rounded-lg px-4 py-2.5 text-sm font-medium">
              {goalTarget != null ? "Update goal" : "Set goal"}
            </button>
          </div>
        </div>
      </div>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,500;0,600;1,500&family=Inter:wght@400;500;600&display=swap');

        .page { background: #EEF1EC; font-family: 'Inter', sans-serif; }
        .serif { font-family: 'Fraunces', serif; }
        .eyebrow { color: #5C7C6F; }
        .heading { color: #1F3D34; font-family: 'Fraunces', serif; }
        .muted { color: #5B685F; }
        .label { color: #5B685F; }
        .hint { color: #9AA69E; }
        .section-title { color: #26302A; }

        .card { background: #FFFFFF; box-shadow: 0 1px 2px rgba(20,30,25,0.06); }
        .card-dark { background: linear-gradient(180deg, #1B372F 0%, #123128 100%); color: #FFFFFF; }
        .dim { color: rgba(255,255,255,0.55); }
        .dim2 { color: rgba(255,255,255,0.4); }
        .dim3 { color: rgba(255,255,255,0.7); }

        .input { width: 100%; padding: 9px 12px; border-radius: 8px; border: 1px solid #DDE3DE; font-size: 14px; color: #26302A; background: #FBFCFB; transition: border-color 0.15s ease; }
        .input:focus { outline: none; border-color: #1F3D34; }

        .btn-primary { background: #1F3D34; color: #FFFFFF; border: none; box-shadow: 0 1px 2px rgba(20,30,25,0.15); transition: background 0.15s ease, transform 0.1s ease; }
        .btn-primary:hover { background: #163027; }
        .btn-primary:active { transform: scale(0.98); }
        .btn-primary:disabled { opacity: 0.75; }
        .btn-arrow { transition: transform 0.15s ease; }
        .btn-primary:hover .btn-arrow { transform: translateX(3px); }

        .btn-white { background: #FFFFFF; color: #1F3D34; border: none; transition: transform 0.1s ease, background 0.15s ease; }
        .btn-white:hover { background: #F2F5F1; }
        .btn-white:active { transform: scale(0.97); }

        .btn-ghost { background: transparent; color: #5B685F; border: 1px solid #DDE3DE; transition: background 0.15s ease; }
        .btn-ghost:hover { background: #FFFFFF; }

        .stress-btn { padding: 9px 16px; border-radius: 8px; font-size: 14px; border: 1px solid #DDE3DE; background: #FBFCFB; color: #3C463F; transition: all 0.15s ease; display: inline-flex; align-items: center; gap: 6px; }
        .stress-btn:hover { border-color: #1F3D34; }
        .stress-btn-selected { background: #1F3D34; border-color: #1F3D34; color: #FFFFFF; transform: scale(1.03); }
        .stress-check { font-size: 12px; }

        .stepper { display: flex; align-items: stretch; border-radius: 8px; border: 1px solid #DDE3DE; background: #FBFCFB; overflow: hidden; }
        .stepper-btn { padding: 0 12px; color: #5B685F; background: transparent; border: none; font-size: 16px; line-height: 1; transition: background 0.15s ease; }
        .stepper-btn:hover { background: #EEF1EC; }
        .stepper-btn-right { border-left: 1px solid #DDE3DE; }
        .stepper-input { flex: 1; min-width: 0; text-align: center; font-size: 14px; color: #26302A; background: transparent; border: none; outline: none; }
        .stepper-input::-webkit-outer-spin-button, .stepper-input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
        .stepper-input { -moz-appearance: textfield; }
        .stepper-unit { display: flex; align-items: center; padding-right: 8px; font-size: 12px; color: #9AA69E; }

        .bar-fill { transition: width 0.6s cubic-bezier(0.22, 1, 0.36, 1); }
        .bar-track { background: rgba(255,255,255,0.1); }

        .factor-row { width: 100%; background: transparent; border: none; padding: 0; cursor: pointer; }
        .factor-chevron { color: rgba(255,255,255,0.4); font-size: 13px; }
        .factor-detail { background: rgba(255,255,255,0.06); border-radius: 8px; padding: 8px 10px; margin-top: 6px; font-size: 11px; color: rgba(255,255,255,0.8); line-height: 1.5; }

        .model-badge { font-size: 11px; color: rgba(255,255,255,0.4); margin-top: 6px; letter-spacing: 0.02em; }

        .channel-btn { padding: 6px 14px; border-radius: 999px; font-size: 12px; border: 1px solid #DDE3DE; background: #FBFCFB; color: #5B685F; transition: all 0.15s ease; }
        .channel-btn:hover { border-color: #1F3D34; }
        .channel-btn-selected { background: #1F3D34; border-color: #1F3D34; color: #FFFFFF; }

        .export-link { background: transparent; border: none; color: rgba(255,255,255,0.5); cursor: pointer; transition: color 0.15s ease; }
        .export-link:hover { color: #FFFFFF; }

        .info-wrap { position: relative; display: inline-flex; margin-left: 5px; }
        .info-btn { width: 15px; height: 15px; border-radius: 50%; border: 1px solid #9AA69E; color: #9AA69E; font-size: 10px; line-height: 1; display: inline-flex; align-items: center; justify-content: center; background: transparent; cursor: pointer; padding: 0; }
        .info-btn:hover { border-color: #1F3D34; color: #1F3D34; }
        .info-bubble { position: absolute; bottom: 130%; left: 50%; transform: translateX(-50%); background: #1F3D34; color: #fff; font-size: 11px; line-height: 1.5; padding: 8px 10px; border-radius: 8px; width: 200px; z-index: 20; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }

        .gauge-arc-in { stroke-dasharray: 245; stroke-dashoffset: 245; animation: drawArc 0.9s cubic-bezier(0.22, 1, 0.36, 1) forwards; }
        @keyframes drawArc { to { stroke-dashoffset: 0; } }
        .gauge-dot { filter: drop-shadow(0 1px 3px rgba(0,0,0,0.4)); }

        .error-icon { width: 44px; height: 44px; border-radius: 50%; border: 2px solid #C8593F; color: #E08A6B; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 600; }

        .spin-slow { animation: spin 2.4s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }

        @keyframes popIn { 0% { opacity: 0; transform: translateY(8px); } 100% { opacity: 1; transform: translateY(0); } }
        .pop-in { animation: popIn 0.45s cubic-bezier(0.22, 1, 0.36, 1); }
        @keyframes fadeIn { 0% { opacity: 0; } 100% { opacity: 1; } }
        .fade-in { animation: fadeIn 0.4s ease; }
      `}</style>
    </div>
  );
}

function Section({ title, children, noBorder }) {
  return (
    <div className="mb-6 pb-6" style={{ borderBottom: noBorder ? "none" : "1px solid #EEF1EC" }}>
      <h3 className="section-title text-[15px] font-medium mb-4">{title}</h3>
      {children}
    </div>
  );
}
function Row({ children }) {
  return <div className="grid gap-4 mb-4 last:mb-0" style={{ gridTemplateColumns: `repeat(${React.Children.count(children)}, 1fr)` }}>{children}</div>;
}
function Field({ label, hint, info, children }) {
  return (
    <div>
      <label className="label text-[13px] flex items-center mb-1.5">
        {label}{info && <Info text={info} />}
      </label>
      {children}
      {hint && <span className="hint text-[11px] block mt-1">{hint}</span>}
    </div>
  );
}
function NumberField({ label, unit, hint, info, value, onChange, min = 0, max = 999, step = 1 }) {
  const clamp = (v) => Math.min(max, Math.max(min, v));
  const dec = () => onChange(Math.round(clamp(value - step) * 10) / 10);
  const inc = () => onChange(Math.round(clamp(value + step) * 10) / 10);
  return (
    <div>
      <label className="label text-[13px] flex items-center mb-1.5">
        {label}{info && <Info text={info} />}
      </label>
      <div className="stepper">
        <button type="button" onClick={dec} className="stepper-btn">−</button>
        <input type="number" value={value} onChange={(e) => onChange(clamp(Number(e.target.value)))} className="stepper-input" />
        {unit && <span className="stepper-unit">{unit}</span>}
        <button type="button" onClick={inc} className="stepper-btn stepper-btn-right">+</button>
      </div>
      {hint && <span className="hint text-[11px] block mt-1">{hint}</span>}
    </div>
  );
}
