import { useEffect, useState } from "react";
import { previewDraft } from "./api";
import type { Army, Config, Kind } from "./types";

export type SetupState = {
  ruleset: "Classic" | "Expanded";
  human_army: Army;
  opponent: string;
  first_army: Army;
  deployment: "fixed" | "random";
  seed: number;
  roster: Kind[] | null;
};

export const initialSetup: SetupState = {
  ruleset: "Classic",
  human_army: "Blue",
  opponent: "heuristic",
  first_army: "Blue",
  deployment: "fixed",
  seed: 42,
  roster: null,
};

type Props = {
  config: Config;
  initial?: SetupState;
  onStart: (setup: SetupState) => void;
  busy?: boolean;
  error?: string;
};

export function Setup({
  config,
  initial = initialSetup,
  onStart,
  busy,
  error,
}: Props) {
  const [setup, setSetup] = useState<SetupState>(initial);
  const [roster, setRoster] = useState<Kind[]>(
    initial.roster ?? ["infantry", "cavalry", "artillery"],
  );
  const [warning, setWarning] = useState("");
  const [preview, setPreview] = useState<Kind[]>([]);
  const costs = config.draft.units;
  const gold = roster.reduce((sum, kind) => sum + costs[kind].gold, 0);
  const people = roster.reduce((sum, kind) => sum + costs[kind].manpower, 0);

  useEffect(() => {
    if (setup.ruleset !== "Expanded") return;
    let cancelled = false;
    previewDraft(roster, setup.opponent, setup.human_army, setup.seed)
      .then((data) => {
        if (!cancelled) setPreview(data.ai_roster);
      })
      .catch(() => {
        if (!cancelled) setPreview([]);
      });
    return () => {
      cancelled = true;
    };
  }, [roster, setup.ruleset, setup.opponent, setup.human_army, setup.seed]);

  function mode(value: "Classic" | "Expanded") {
    setSetup({
      ...setup,
      ruleset: value,
      opponent: value === "Classic" ? "heuristic" : "balanced",
      deployment: value === "Classic" ? "fixed" : "random",
    });
    setWarning("");
  }
  function buy(kind: Kind) {
    if (roster.length >= config.draft.maximum) {
      setWarning("Formation limit reached");
      return;
    }
    if (gold + costs[kind].gold > config.draft.gold) {
      setWarning("Not enough gold");
      return;
    }
    if (people + costs[kind].manpower > config.draft.manpower) {
      setWarning("Manpower capacity exceeded");
      return;
    }
    setRoster([...roster, kind]);
    setWarning("");
  }
  function remove(index: number) {
    setRoster(roster.filter((_, i) => i !== index));
    setWarning("");
  }

  return (
    <div className="setup-layout page-enter">
      <div className="section-heading">
        <div>
          <span className="eyebrow">PREPARE YOUR CAMPAIGN</span>
          <h1>Choose your command.</h1>
          <p>
            Set the conditions. Build your force. Every order from here is
            yours.
          </p>
        </div>
        <div className="section-number">01 / SETUP</div>
      </div>
      <div className="setup-columns">
        <section className="panel setup-main">
          <div className="panel-title">
            <span className="panel-index">01</span>
            <h2>Rules of engagement</h2>
          </div>
          <div className="segmented" role="group" aria-label="Ruleset">
            {(["Classic", "Expanded"] as const).map((value) => (
              <button
                key={value}
                className={setup.ruleset === value ? "active" : ""}
                onClick={() => mode(value)}
              >
                {value}
                <small>
                  {value === "Classic"
                    ? "Original three formations"
                    : "Draft your own army"}
                </small>
              </button>
            ))}
          </div>
          <div className="field-grid">
            <label>
              Your army
              <select
                aria-label="Your army"
                value={setup.human_army}
                onChange={(e) =>
                  setSetup({ ...setup, human_army: e.target.value as Army })
                }
              >
                <option>Blue</option>
                <option>Red</option>
              </select>
            </label>
            <label>
              First move
              <select
                aria-label="First move"
                value={setup.first_army}
                onChange={(e) =>
                  setSetup({ ...setup, first_army: e.target.value as Army })
                }
              >
                <option>Blue</option>
                <option>Red</option>
              </select>
            </label>
            <label>
              Opponent
              <select
                aria-label="Opponent"
                value={setup.opponent}
                onChange={(e) =>
                  setSetup({ ...setup, opponent: e.target.value })
                }
              >
                {(setup.ruleset === "Classic"
                  ? config.classic_opponents
                  : config.expanded_opponents
                ).map((name) => (
                  <option key={name} value={name}>
                    {name === "ppo"
                      ? "Trained PPO"
                      : `${name[0].toUpperCase()}${name.slice(1)}${setup.ruleset === "Expanded" ? " doctrine" : " general"}`}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Deployment
              <select
                aria-label="Deployment"
                value={setup.deployment}
                disabled={setup.ruleset === "Expanded"}
                onChange={(e) =>
                  setSetup({
                    ...setup,
                    deployment: e.target.value as "fixed" | "random",
                  })
                }
              >
                <option value="fixed">Fixed</option>
                <option value="random">Seeded random</option>
              </select>
            </label>
            <label>
              Battle seed
              <input
                aria-label="Battle seed"
                type="number"
                min="0"
                max="2147483647"
                value={setup.seed}
                onChange={(e) =>
                  setSetup({
                    ...setup,
                    seed: Math.max(0, Number(e.target.value)),
                  })
                }
              />
            </label>
          </div>
        </section>
        <section className="panel roster-panel">
          <div className="panel-title">
            <span className="panel-index">02</span>
            <h2>
              {setup.ruleset === "Expanded"
                ? "Assemble your army"
                : "Classic formation"}
            </h2>
          </div>
          {setup.ruleset === "Expanded" ? (
            <>
              <div className="resource-row">
                <div>
                  <strong>{(config.draft.gold - gold).toLocaleString()}</strong>
                  <span>GOLD LEFT</span>
                </div>
                <div>
                  <strong>{config.draft.manpower - people}</strong>
                  <span>MANPOWER LEFT</span>
                </div>
                <div>
                  <strong>{config.draft.maximum - roster.length}</strong>
                  <span>SLOTS LEFT</span>
                </div>
              </div>
              <div className="unit-market">
                {(Object.keys(costs) as Kind[]).map((kind) => (
                  <div className="market-card" key={kind}>
                    <div className={`market-icon ${kind}`}>
                      {kind[0].toUpperCase()}
                    </div>
                    <div>
                      <strong>{kind[0].toUpperCase() + kind.slice(1)}</strong>
                      <small>
                        {costs[kind].gold.toLocaleString()} gold ·{" "}
                        {costs[kind].manpower} manpower
                      </small>
                      <small>
                        HP {costs[kind].health} · Move {costs[kind].movement} ·
                        Range {costs[kind].attack_range}
                      </small>
                    </div>
                    <button
                      aria-label={`Recruit ${kind}`}
                      onClick={() => buy(kind)}
                    >
                      +
                    </button>
                  </div>
                ))}
              </div>
              <div className="roster-list">
                <span className="mini-heading">
                  YOUR FORMATIONS · {roster.length}/{config.draft.maximum}
                </span>
                {roster.map((kind, index) => (
                  <div key={`${kind}-${index}`} className="roster-slot">
                    <span>
                      {String(index + 1).padStart(2, "0")} &nbsp;{" "}
                      {kind.toUpperCase()}
                    </span>
                    <button
                      aria-label={`Remove ${kind} ${index + 1}`}
                      onClick={() => remove(index)}
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
              <div className="ai-preview">
                <span className="mini-heading">
                  ENEMY INTELLIGENCE · {setup.opponent.toUpperCase()}
                </span>
                <p>
                  {preview.length
                    ? preview
                        .map((k) => k[0].toUpperCase() + k.slice(1))
                        .join(" / ")
                    : "Preparing draft…"}
                </p>
                <small>
                  Programmed drafting doctrine, not a trained neural network.
                </small>
              </div>
            </>
          ) : (
            <div className="classic-roster">
              <p>Two equal armies. Three formations each.</p>
              <div>
                INFANTRY <span>·</span> CAVALRY <span>·</span> ARTILLERY
              </div>
              <small>
                Classic keeps the original research rules and checkpoint
                encoding intact.
              </small>
            </div>
          )}
          {(warning || error) && (
            <p className="form-error" role="alert">
              {warning || error}
            </p>
          )}
          <button
            className="primary-button start-button"
            disabled={busy || (setup.ruleset === "Expanded" && !roster.length)}
            onClick={() =>
              onStart({
                ...setup,
                roster: setup.ruleset === "Expanded" ? roster : null,
              })
            }
          >
            {busy ? "Preparing battlefield…" : "Begin battle"} <span>↗</span>
          </button>
        </section>
      </div>
    </div>
  );
}
