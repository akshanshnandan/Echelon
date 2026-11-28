import { useEffect, useRef, useState } from "react";
import { Battlefield } from "./Battlefield";
import { CommandView, createCommand } from "./CommandView";
import type { CommandGame } from "./CommandView";
import { CommandReplayView } from "./CommandReplayView";
import { validateCommandReplay } from "./commandReplay";
import type { CommandReplay } from "./commandReplay";
import { LandingBattle } from "./LandingBattle";
import { analyticsBlocked, analyticsConsent, configureAnalytics, setAnalyticsConsent, track, trackCompletion, trackError } from "./analytics";
import {
  commandSampleReplay,
  createGame,
  getConfig,
  getReplay,
  sendFeedback,
  sampleReplay,
  submitOrder,
} from "./api";
import { replaySnapshot, validateReplay } from "./replay";
import { Setup, initialSetup } from "./Setup";
import type { SetupState } from "./Setup";
import type { Config, Game, Order, OrderKind, Replay } from "./types";

type View = "home" | "play" | "replay" | "lab";
const orderKinds: OrderKind[] = ["HOLD", "ADVANCE", "ATTACK", "RETREAT"];
const github = "https://github.com/akshanshnandan/Echelon";

function brand() {
  return (
    <span className="brand">
      <span className="brand-mark">✦</span> ECHELON
      <span className="brand-dot">.</span>
    </span>
  );
}

export default function App() {
  const [view, setView] = useState<View>("home");
  const [config, setConfig] = useState<Config | null>(null);
  const [game, setGame] = useState<Game | null>(null);
  const [commandGame, setCommandGame] = useState<CommandGame | null>(null);
  const [setup, setSetup] = useState<SetupState>(initialSetup);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [expiredGame, setExpiredGame] = useState(false);
  const [consent, setConsent] = useState<"on" | "off" | null>(analyticsConsent);
  const [privacyOpen, setPrivacyOpen] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackStatus, setFeedbackStatus] = useState("");
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [rating, setRating] = useState(3);
  const [category, setCategory] = useState("gameplay");
  const visited = useRef<View | null>(null);
  const battleStarted = useRef(new Map<string, number>());
  const [selected, setSelected] = useState<string | null>(null);
  const [mode, setMode] = useState<OrderKind>("ADVANCE");
  const [replay, setReplay] = useState<Replay | null>(null);
  const [commandReplay, setCommandReplay] = useState<CommandReplay | null>(null);
  const [replayIndex, setReplayIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const file = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getConfig()
      .then((next) => {setConfig(next); if (next.analytics) configureAnalytics(next.analytics);})
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (!config || visited.current === view) return;
    visited.current = view;
    void track("page_view", {page:view});
    if (view === "play") void track("play_opened");
  }, [config, view]);

  function chooseAnalytics(enabled: boolean) {
    if (enabled && analyticsBlocked()) return;
    setAnalyticsConsent(enabled);
    setConsent(enabled ? "on" : "off");
  }

  async function feedback() {
    setFeedbackBusy(true);
    setFeedbackStatus("");
    try { await sendFeedback(rating,category); setFeedbackStatus("Thanks. Your rating was received."); }
    catch (e) { setFeedbackStatus((e as Error).message); trackError("feedback","network"); }
    finally { setFeedbackBusy(false); }
  }
  useEffect(() => {
    if (!playing || !replay) return;
    const timer = window.setInterval(
      () =>
        setReplayIndex((index) => {
          if (index >= replay.decisions.length) {
            setPlaying(false);
            return index;
          }
          return index + 1;
        }),
      950 / speed,
    );
    return () => window.clearInterval(timer);
  }, [playing, replay, speed]);

  async function start(next: SetupState) {
    setBusy(true);
    setError("");
    setExpiredGame(false);
    try {
      if (next.ruleset === "Command") {
        const created = await createCommand({human_army: next.human_army, opponent: next.opponent, map: next.map, seed: next.seed, size: next.size, roster: next.roster});
        battleStarted.current.set(created.id, performance.now());
        void track("battle_started", {mode:"Command",map:next.map,opponent:next.opponent});
        setCommandGame(created);
        setGame(null);
        setSetup(next);
        return;
      }
      const { map: _map, size: _size, ...legacySetup } = next;
      const created = await createGame(legacySetup);
      battleStarted.current.set(created.id, performance.now());
      void track("battle_started", {mode:created.ruleset,opponent:created.opponent});
      setCommandGame(null);
      setSetup(next);
      setGame(created);
      setSelected(null);
      setMode("ADVANCE");
    } catch (e) {
      setError((e as Error).message);
      trackError("setup","rejected");
    } finally {
      setBusy(false);
    }
  }
  async function order(chosen: Order) {
    if (!game || busy || expiredGame || game.state.finished) return;
    setBusy(true);
    setError("");
    try {
      const updated = await submitOrder(game.id, chosen);
      setGame(updated);
      if (updated.state.finished) trackCompletion(updated.id, {mode:updated.ruleset,opponent:updated.opponent,
        duration_seconds:Math.round((performance.now()-(battleStarted.current.get(updated.id) ?? performance.now()))/1000),
        winner:updated.state.winner ?? "draw"});
      setSelected(null);
    } catch (e) {
      setError((e as Error).message);
      const expired=(e as Error).message.startsWith("Game session expired");
      if (expired) setExpiredGame(true);
      trackError("order",expired?"expired":"rejected");
    } finally {
      setBusy(false);
    }
  }
  function changeMode(kind: OrderKind) {
    setMode(kind);
    if (kind === "HOLD" && selected) {
      const hold = game?.legal_orders.find(
        (o) => o.unit_id === selected && o.kind === "HOLD",
      );
      if (hold) void order(hold);
    }
  }
  function selectUnit(id: string) {
    if (mode === "HOLD") {
      const hold = game?.legal_orders.find(
        (candidate) => candidate.unit_id === id && candidate.kind === "HOLD",
      );
      if (hold) void order(hold);
    } else {
      setSelected(id);
    }
  }
  function newBattle() {
    setGame(null);
    setCommandGame(null);
    setSelected(null);
    setExpiredGame(false);
    setView("play");
  }
  async function download() {
    if (!game) return;
    try {
      const record = await getReplay(game.id);
      void track("replay_downloaded", {mode:game.ruleset});
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(record, null, 2)], {
          type: "application/json",
        }),
      );
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `echelon-${game.ruleset.toLowerCase()}-${game.seed}.json`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError((e as Error).message);
      const expired=(e as Error).message.startsWith("Game session expired");
      if (expired) setExpiredGame(true);
      trackError("replay",expired?"expired":"network");
    }
  }
  async function loadSample(ruleset: "classic" | "expanded") {
    setError("");
    try {
      setReplay(validateReplay(await sampleReplay(ruleset)));
      setCommandReplay(null);
      setReplayIndex(0);
      setPlaying(false);
      setView("replay");
    } catch (e) {
      setError((e as Error).message);
      trackError("replay","network");
    }
  }
  async function upload(event: React.ChangeEvent<HTMLInputElement>) {
    const upload = event.target.files?.[0];
    if (!upload) return;
    setError("");
    try {
      if (upload.size > 6_000_000) throw new Error("Replay exceeds 6 MB");
      const value = JSON.parse(await upload.text());
      if (value?.version === 3 && value?.ruleset === "Command") {
        setCommandReplay(validateCommandReplay(value));
        setReplay(null);
      } else {
        setReplay(validateReplay(value));
        setCommandReplay(null);
      }
      setReplayIndex(0);
      setPlaying(false);
    } catch (e) {
      setError((e as Error).message);
      trackError("replay","rejected");
    }
    event.target.value = "";
  }
  const last = game?.history[game.history.length - 1];
  const selectedUnit = selected ? game?.state.units[selected] : null;
  const survivors = game
    ? Object.values(game.state.units).filter(
        (u) => u.army === game.human_army && u.effective,
      ).length
    : 0;
  const damage =
    game?.history
      .filter((step) => step.army === game.human_army)
      .reduce((sum, step) => sum + step.damage, 0) ?? 0;

  return (
    <div className="app-shell">
      <header className="site-header">
        <button className="logo-button" onClick={() => setView("home")}>
          {brand()}
        </button>
        <nav aria-label="Main navigation">
          <button
            className={view === "home" ? "nav-active" : ""}
            onClick={() => setView("home")}
          >
            Home
          </button>
          <button
            className={view === "play" ? "nav-active" : ""}
            onClick={() => setView("play")}
          >
            Play
          </button>
          <button
            className={view === "replay" ? "nav-active" : ""}
            onClick={() => setView("replay")}
          >
            Replays
          </button>
          <button
            className={view === "lab" ? "nav-active" : ""}
            onClick={() => setView("lab")}
          >
            AI Laboratory
          </button>
        </nav>
        <a
          className="header-github"
          href={github}
          target="_blank"
          rel="noreferrer"
        >
          GitHub ↗
        </a>
      </header>

      {view === "home" && (
        <main className="home page-enter">
          <section className="hero">
            <div className="hero-copy">
              <div className="eyebrow">
                <span className="live-indicator" /> A HISTORICAL STRATEGY GAME
              </div>
              <h1>
                Command the line.
                <br />
                <em>Change the outcome.</em>
              </h1>
              <p>
                Direct formations in real time, build a custom army, or play the
                deterministic battle that began Echelon's AI research.
              </p>
              <div className="hero-actions">
                <button
                  className="primary-button"
                  onClick={() => setView("play")}
                >
                  Play Echelon <span>↗</span>
                </button>
                <button
                  className="secondary-button"
                  onClick={() => setView("lab")}
                >
                  Explore the AI Lab <span>→</span>
                </button>
              </div>
              <div className="hero-meta">
                <div>
                  <strong>08 × 08</strong>
                  <span>BATTLEFIELD</span>
                </div>
                <div>
                  <strong>02</strong>
                  <span>GAME MODES</span>
                </div>
                <div>
                  <strong>04</strong>
                  <span>AI DOCTRINES</span>
                </div>
              </div>
            </div>
            <LandingBattle onPlay={() => setView("play")} />
            <div className="hero-visual" aria-label="Battlefield preview">
              <div className="visual-top">
                <span>FIELD REPORT / 001</span>
                <span>BLUE vs RED</span>
              </div>
              <div className="preview-grid">
                {Array.from({ length: 64 }, (_, i) => (
                  <div
                    key={i}
                    className={`preview-cell ${i % 2 ? "shaded" : ""}`}
                  >
                    {i === 10 || i === 19 || i === 25 ? (
                      <span className="preview-unit blue-chip">
                        {i === 19 ? "C" : "I"}
                      </span>
                    ) : i === 38 || i === 44 || i === 53 ? (
                      <span className="preview-unit red-chip">
                        {i === 44 ? "A" : "C"}
                      </span>
                    ) : i === 28 ? (
                      <span className="preview-target" />
                    ) : null}
                  </div>
                ))}
              </div>
              <div className="visual-bottom">
                <span>TURN 08 / 30</span>
                <span className="gold-text">● ENGAGEMENT IN PROGRESS</span>
              </div>
            </div>
          </section>
          <section className="mode-ledger" aria-label="Game modes">
            <div><span>01 / COMMAND</span><h2>Real-time warfare</h2><p>Move formations together, seize the center, and pause to read the field.</p></div>
            <div><span>02 / EXPANDED</span><h2>Draft your army</h2><p>Spend gold and manpower on the force you want to lead.</p></div>
            <div><span>03 / CLASSIC</span><h2>The original campaign</h2><p>Play the exact turn-based rules behind Echelon's AI research.</p></div>
          </section>
          <section className="feature-strip">
            <div>
              <span>01 / COMMAND</span>
              <h3>Every order matters</h3>
              <p>
                Choose a formation, study its legal moves, and shape each turn.
              </p>
            </div>
            <div>
              <span>02 / COMPOSE</span>
              <h3>Build your force</h3>
              <p>
                Draft infantry, cavalry, and artillery within real resource
                limits.
              </p>
            </div>
            <div>
              <span>03 / INVESTIGATE</span>
              <h3>Watch AI evolve</h3>
              <p>
                Compare programmed doctrine with measured reinforcement learning
                results.
              </p>
            </div>
          </section>
        </main>
      )}

      {view === "play" && (
        <main className="content-wrap">
          {!game && !commandGame ? (
            config ? (
              <Setup
                config={config}
                initial={setup}
                onStart={start}
                busy={busy}
                error={error}
              />
            ) : (
              <div className="loading">
                {error || "Preparing command center…"}
              </div>
            )
          ) : commandGame ? (
            <CommandView initial={commandGame} onNew={newBattle} onReplay={(record) => {setCommandReplay(validateCommandReplay(record));setReplay(null);setView("replay");}} />
          ) : game ? (
            <div className="game-view page-enter">
              <div className="battle-header">
                <div>
                  <span className="eyebrow">
                    LIVE BATTLE · {game.ruleset.toUpperCase()}
                  </span>
                  <h1>
                    {game.human_army} command{" "}
                    <span className="versus">vs.</span> {game.opponent}
                  </h1>
                </div>
                <div className="battle-status">
                  <span>
                    ROUND <strong>{game.round} / 30</strong>
                  </span>
                  <span>
                    ACTIVE{" "}
                    <strong>
                      {game.state.finished
                        ? "BATTLE ENDED"
                        : game.state.active_army}
                    </strong>
                  </span>
                </div>
              </div>
              <div className="game-layout">
                <section className="board-panel panel">
                  <div className="board-topline">
                    <span>THE BATTLEFIELD</span>
                    <span>
                      SEED {game.seed} · {game.first_army.toUpperCase()} FIRST
                    </span>
                  </div>
                  <Battlefield
                    state={game.state}
                    human={game.human_army}
                    orders={game.legal_orders}
                    selected={selected}
                    mode={mode}
                    latest={last}
                    onSelect={selectUnit}
                    onOrder={(o) => void order(o)}
                  />
                  <div className="board-legend">
                    <span>
                      <i className="legend-dot blue-dot" /> BLUE
                    </span>
                    <span>
                      <i className="legend-dot red-dot" /> RED
                    </span>
                    <span>
                      <i className="legend-dot move-dot" /> LEGAL MOVE
                    </span>
                    <span>
                      <i className="legend-dot attack-dot" /> ATTACK TARGET
                    </span>
                  </div>
                </section>
                <aside className="command-column">
                  <section className="panel command-panel">
                    <div className="panel-title">
                      <span className="panel-index">01</span>
                      <h2>Issue an order</h2>
                    </div>
                    {game.state.finished ? (
                      <div className="result-block" data-testid="battle-result">
                        <span className="eyebrow">BATTLE COMPLETE</span>
                        <h2>
                          {game.state.winner === game.human_army
                            ? "Victory"
                            : game.state.winner
                              ? "Defeat"
                              : "Draw"}
                        </h2>
                        <p>
                          {game.state.winner ?? "Neither army"}{" "}
                          {game.state.winner ? "wins" : "holds"} by{" "}
                          {game.state.reason === "elimination"
                            ? "elimination"
                            : "30-round tiebreak"}
                          .
                        </p>
                        <div className="result-stats">
                          <span>{survivors} SURVIVORS</span>
                          <span>{damage} DAMAGE DEALT</span>
                        </div>
                        <div className="result-actions">
                          <button onClick={() => void start(setup)}>
                            Restart
                          </button>
                          <button onClick={newBattle}>New battle</button>
                          <button onClick={() => void download()}>
                            Download replay ↓
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <p className="instruction">
                          {selectedUnit
                            ? `${selected} · ${selectedUnit.kind.toUpperCase()} · ${selectedUnit.health} HP · ${selectedUnit.morale} morale`
                            : "Select one of your living formations on the board."}
                        </p>
                        <div className="order-grid">
                          {orderKinds.map((kind, index) => (
                            <button
                              data-testid={`order-${kind.toLowerCase()}`}
                              key={kind}
                              className={mode === kind ? "order-active" : ""}
                              onClick={() => changeMode(kind)}
                            >
                              <span>0{index + 1}</span>
                              {kind}
                            </button>
                          ))}
                        </div>
                        <p className="order-hint">
                          {mode === "HOLD"
                            ? "Hold issues immediately after a formation is selected."
                            : mode === "ATTACK"
                              ? "Select a gold-ringed enemy target."
                              : `Select a highlighted ${mode === "RETREAT" ? "blue" : "green"} square.`}
                        </p>
                      </>
                    )}
                    {error && (
                      <p className="form-error" role="alert">{error} {expiredGame && <button onClick={newBattle}>New battle</button>}</p>
                    )}
                  </section>
                  <section className="panel log-panel">
                    <div className="panel-title">
                      <span className="panel-index">02</span>
                      <h2>Battle dispatches</h2>
                    </div>
                    <div className="battle-log">
                      {game.history.length ? (
                        game.history
                          .slice(-7)
                          .reverse()
                          .map((step, i) => (
                            <div
                              className="log-item"
                              key={game.history.length - i}
                            >
                              <span className={step.army.toLowerCase()}>
                                {step.army.slice(0, 1)} · R{step.round}
                              </span>
                              <p>{step.message}</p>
                            </div>
                          ))
                      ) : (
                        <p className="empty-log">
                          The field is quiet. Your first command awaits.
                        </p>
                      )}
                    </div>
                  </section>
                </aside>
              </div>
            </div>
          ) : null}
        </main>
      )}

      {view === "replay" && (
        <main className="content-wrap replay-page page-enter">
          <div className="section-heading">
            <div>
              <span className="eyebrow">AFTER ACTION ARCHIVE</span>
              <h1>Study the battle.</h1>
              <p>
                Step through recorded decisions. The viewer reads snapshots; it
                never calculates combat.
              </p>
            </div>
            <div className="section-number">03 / REPLAY</div>
          </div>
          <div className="replay-toolbar">
            <button onClick={() => {setError("");void commandSampleReplay().then((record) => {setCommandReplay(validateCommandReplay(record));setReplay(null);}).catch((e) => {setError(e.message);trackError("replay","network");});}}>Open Command sample</button>
            <button onClick={() => void loadSample("classic")}>
              Open Classic sample
            </button>
            <button onClick={() => void loadSample("expanded")}>
              Open Expanded sample
            </button>
            <button onClick={() => file.current?.click()}>
              Upload JSON replay
            </button>
            <input
              ref={file}
              type="file"
              accept=".json,application/json"
              hidden
              onChange={(e) => void upload(e)}
            />
          </div>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          {commandReplay ? <CommandReplayView record={commandReplay} /> : replay ? (
            <div className="replay-layout">
              <section className="panel board-panel">
                <div className="board-topline">
                  <span>REPLAY / {replay.ruleset ?? "CLASSIC"}</span>
                  <span>SEED {replay.seed}</span>
                </div>
                <Battlefield
                  state={replaySnapshot(replay, replayIndex)}
                  latest={replay.decisions[Math.max(0, replayIndex - 1)]}
                />
                <div className="replay-controls">
                  <button
                    aria-label="Previous action"
                    onClick={() => {
                      setPlaying(false);
                      setReplayIndex(Math.max(0, replayIndex - 1));
                    }}
                  >
                    ←
                  </button>
                  <button
                    aria-label={playing ? "Pause replay" : "Play replay"}
                    onClick={() => setPlaying(!playing)}
                  >
                    {playing ? "Pause" : "Play"}
                  </button>
                  <button
                    aria-label="Next action"
                    onClick={() => {
                      setPlaying(false);
                      setReplayIndex(
                        Math.min(replay.decisions.length, replayIndex + 1),
                      );
                    }}
                  >
                    →
                  </button>
                  <select
                    aria-label="Replay speed"
                    value={speed}
                    onChange={(e) => setSpeed(Number(e.target.value))}
                  >
                    <option value={0.5}>0.5×</option>
                    <option value={1}>1×</option>
                    <option value={2}>2×</option>
                    <option value={4}>4×</option>
                  </select>
                  <span>
                    {replayIndex} / {replay.decisions.length} ORDERS
                  </span>
                </div>
              </section>
              <aside className="panel replay-notes">
                <span className="eyebrow">RECORDED COMMAND</span>
                <h2>
                  {replayIndex
                    ? replay.decisions[replayIndex - 1].action
                    : "Deployment"}
                </h2>
                <p>
                  {replayIndex
                    ? replay.decisions[replayIndex - 1].message
                    : "The armies take their starting positions."}
                </p>
                <div className="replay-meter">
                  <div
                    style={{
                      width: `${(replayIndex / replay.decisions.length) * 100}%`,
                    }}
                  />
                </div>
                {replayIndex === replay.decisions.length && (
                  <div className="replay-end">
                    <strong>{replay.final.winner ?? "Draw"}</strong>
                    <span>
                      {replay.final.reason === "elimination"
                        ? "DECISIVE VICTORY"
                        : "TIME-LIMIT RESULT"}
                    </span>
                  </div>
                )}
                <div className="archive-meta">
                  {replay.agent_army} perspective · {replay.opponent} opponent ·{" "}
                  {replay.first_army} first
                </div>
              </aside>
            </div>
          ) : (
            <div className="replay-empty panel">
              <div className="archive-glyph">◇</div>
              <h2>Every battle leaves a record.</h2>
              <p>
                Open a bundled battle above or load a JSON recording you
                downloaded after play.
              </p>
            </div>
          )}
        </main>
      )}

      {view === "lab" && (
        <main className="content-wrap lab-page page-enter">
          <div className="section-heading">
            <div>
              <span className="eyebrow">RESEARCH NOTES / VERIFIED RESULTS</span>
              <h1>Inside the AI laboratory.</h1>
              <p>
                What the generals learned, what they did not, and what the
                evidence actually supports.
              </p>
            </div>
            <div className="section-number">04 / RESEARCH</div>
          </div>
          <div className="lab-grid">
            <section className="panel lab-intro">
              <span className="eyebrow">THE EXPERIMENT</span>
              <h2>From random orders to tactical play.</h2>
              <p>
                Classic Echelon trained a MaskablePPO policy using a 63-value
                observation and 396 stable action slots. Legal-action masking
                prevented impossible moves. The model learned from sparse win,
                loss, and draw rewards.
              </p>
              <p>
                The four Expanded drafting doctrines are{" "}
                <strong>programmed strategies</strong>. They are not neural
                networks, and the Classic policy cannot command custom rosters.
              </p>
            </section>
            <section className="panel lab-stat">
              <span>PHASE 7 FINAL TEST</span>
              <strong>97.4%</strong>
              <p>
                Selected trained policy score against RandomGeneral over 400
                matched battles.
              </p>
            </section>
            <section className="panel lab-stat amber">
              <span>PHASE 7 FINAL TEST</span>
              <strong>40.9%</strong>
              <p>
                Selected policy score against HeuristicGeneral over the same
                400-scenario design.
              </p>
            </section>
          </div>
          <section className="panel research-table">
            <div className="panel-title">
              <span className="panel-index">01</span>
              <h2>Frozen checkpoint comparison</h2>
            </div>
            <table>
              <thead>
                <tr>
                  <th>Policy</th>
                  <th>vs Random</th>
                  <th>vs Heuristic</th>
                  <th>Scenario pool</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Phase 5 trained</td>
                  <td>91.0%</td>
                  <td>36.1%</td>
                  <td>Phase 7 final</td>
                </tr>
                <tr>
                  <td>Selected Phase 6 continuation</td>
                  <td>97.4%</td>
                  <td>40.9%</td>
                  <td>Phase 7 final</td>
                </tr>
              </tbody>
            </table>
            <p>
              The observed 4.8-point gain against HeuristicGeneral had a paired
              95% deployment-group interval of −2.0 to +11.4 points. It is{" "}
              <strong>not statistically conclusive</strong>. This page reports
              frozen results; it does not run training or use the reserved
              final-test pool for selection.
            </p>
            <a
              href={github + "/blob/main/docs/phase7_final_test.json"}
              target="_blank"
              rel="noreferrer"
            >
              Read the archived final-test report ↗
            </a>
          </section>
        </main>
      )}

      {consent === null && !!config?.analytics?.token && <section className="beta-notice" aria-label="Analytics choice">
        <p>Optional usage analytics help improve the beta. Analytics stay off until you choose. No accounts, session recordings, or automatic click tracking.</p>
        <button onClick={() => chooseAnalytics(true)}>Enable analytics</button>
        <button onClick={() => chooseAnalytics(false)}>Keep off</button>
        <button onClick={() => setPrivacyOpen(true)}>Privacy details</button>
      </section>}
      {privacyOpen && <section className="beta-panel" aria-label="Privacy notice">
        <h2>Privacy notice</h2>
        <p>Echelon works without an account. Optional PostHog analytics record only named page and game events, mode, map, opponent, battle duration, result, replay downloads, and broad error categories. We do not send game IDs, seeds, orders, typed text, or raw errors. PostHog receives network metadata when events are delivered; location enrichment is disabled. Automatic capture, session replay, and person profiles are disabled. Analytics remain off by default. Your browser's Global Privacy Control or Do Not Track signal keeps them off.</p>
        <p>Game sessions live temporarily in server memory. Optional feedback sends only a rating and fixed category to server logs. The hosting provider may process request metadata under its own retention settings. You can change your analytics choice here at any time.</p>
        <button disabled={analyticsBlocked() || !config?.analytics?.token} onClick={() => chooseAnalytics(true)}>Enable analytics</button>
        <button onClick={() => chooseAnalytics(false)}>Turn analytics off</button>
        <span role="status">Analytics: {!config?.analytics?.token ? "unavailable" : consent === "on" ? "on" : "off"}{analyticsBlocked() ? " (browser privacy signal)" : ""}</span>
        <button onClick={() => setPrivacyOpen(false)}>Close</button>
      </section>}
      {feedbackOpen && <section className="beta-panel" aria-label="Player feedback">
        <h2>Beta feedback</h2><p>No account or written response needed. Choose a rating and topic.</p>
        <label>Rating <select aria-label="Feedback rating" value={rating} onChange={(e) => setRating(Number(e.target.value))}>{[1,2,3,4,5].map((n) => <option key={n} value={n}>{n} / 5</option>)}</select></label>
        <label>Topic <select aria-label="Feedback topic" value={category} onChange={(e) => setCategory(e.target.value)}>{["gameplay","controls","performance","bug","other"].map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
        <button disabled={feedbackBusy} onClick={() => void feedback()}>{feedbackBusy ? "Sending…" : "Send feedback"}</button>
        <button onClick={() => setFeedbackOpen(false)}>Close</button>
        {feedbackStatus && <p role="status">{feedbackStatus}</p>}
      </section>}
      <footer>
        <span>{brand()}</span>
        <span>COMMAND · OBSERVE · LEARN</span>
        <span>Built from deterministic Python battle rules</span>
        <button onClick={() => setPrivacyOpen(true)}>Privacy and analytics</button>
        <button onClick={() => {setFeedbackStatus("");setFeedbackOpen(true);}}>Give feedback</button>
      </footer>
    </div>
  );
}
