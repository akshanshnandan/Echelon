import { useEffect, useRef, useState } from "react";
import { Battlefield } from "./Battlefield";
import {
  createGame,
  getConfig,
  getReplay,
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
  const [setup, setSetup] = useState<SetupState>(initialSetup);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [mode, setMode] = useState<OrderKind>("ADVANCE");
  const [replay, setReplay] = useState<Replay | null>(null);
  const [replayIndex, setReplayIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const file = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getConfig()
      .then(setConfig)
      .catch((e) => setError(e.message));
  }, []);
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
    try {
      const created = await createGame(next);
      setSetup(next);
      setGame(created);
      setSelected(null);
      setMode("ADVANCE");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function order(chosen: Order) {
    if (!game || busy) return;
    setBusy(true);
    setError("");
    try {
      setGame(await submitOrder(game.id, chosen));
      setSelected(null);
    } catch (e) {
      setError((e as Error).message);
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
    setSelected(null);
    setView("play");
  }
  async function download() {
    if (!game) return;
    try {
      const record = await getReplay(game.id);
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
    }
  }
  async function loadSample(ruleset: "classic" | "expanded") {
    setError("");
    try {
      setReplay(validateReplay(await sampleReplay(ruleset)));
      setReplayIndex(0);
      setPlaying(false);
      setView("replay");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function upload(event: React.ChangeEvent<HTMLInputElement>) {
    const upload = event.target.files?.[0];
    if (!upload) return;
    setError("");
    try {
      if (upload.size > 3_000_000) throw new Error("Replay exceeds 3 MB");
      setReplay(validateReplay(JSON.parse(await upload.text())));
      setReplayIndex(0);
      setPlaying(false);
    } catch (e) {
      setError((e as Error).message);
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
                <span className="live-indicator" /> A TACTICAL AI LABORATORY
              </div>
              <h1>
                Command the line.
                <br />
                <em>Change the outcome.</em>
              </h1>
              <p>
                Build your army, read the battlefield, and face programmed
                generals in a strategy game shaped by reinforcement learning
                research.
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
          {!game ? (
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
          ) : (
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
                      <p className="form-error" role="alert">
                        {error}
                      </p>
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
          )}
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
          {replay ? (
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

      <footer>
        <span>{brand()}</span>
        <span>COMMAND · OBSERVE · LEARN</span>
        <span>Built from deterministic Python battle rules</span>
      </footer>
    </div>
  );
}
