import { useEffect, useRef, useState } from "react";

type Unit = { id: string; army: "Blue" | "Red"; kind: string; x: number; y: number; heading: number; health: number; morale: number; effective: boolean; order: string; destination: [number, number] | null; waypoints: [number, number][]; width: number };
export type CommandGame = { id: string; ruleset: "Command"; human_army: "Blue" | "Red"; opponent: string; seed: number; paused: boolean; speed: number; battle: { tick: number; time: number; map: string; units: Record<string, Unit>; objective: Record<string, number>; finished: boolean; winner: string | null; reason: string | null; events: {tick: number; type: string; unit?: string; target?: string}[] } };
async function call<T>(path: string, body?: object): Promise<T> {
  const response = await fetch(`/api/command${path}`, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined);
  if (!response.ok) { const problem = await response.json(); throw new Error(typeof problem.detail === "string" ? problem.detail : "Command request failed"); }
  return response.json();
}
export async function createCommand(setup: object) { return call<CommandGame>("", setup); }

export function CommandView({ initial, onNew }: { initial: CommandGame; onNew: () => void }) {
  const [game, setGame] = useState(initial);
  const [drawn, setDrawn] = useState<Record<string, {x: number; y: number; heading: number}>>(() => Object.fromEntries(Object.values(initial.battle.units).map((u) => [u.id, {x: u.x, y: u.y, heading: u.heading}])));
  const drawnRef = useRef(drawn);
  const [selected, setSelected] = useState<string[]>([]);
  const [mode, setMode] = useState<"MOVE" | "ATTACK" | "DEFEND">("MOVE");
  const [error, setError] = useState("");
  const [zoom, setZoom] = useState(1);
  const svg = useRef<SVGSVGElement>(null);
  useEffect(() => {
    const timer = window.setInterval(() => { void call<CommandGame>(`/${initial.id}`).then(setGame).catch((e) => setError(e.message)); }, 150);
    return () => window.clearInterval(timer);
  }, [initial.id]);
  useEffect(() => {
    const from = drawnRef.current;
    const target = game.battle.units;
    const start = performance.now();
    let frame = 0;
    function animate(now: number) {
      const t = Math.min(1, (now - start) / 150);
      const next = Object.fromEntries(Object.values(target).map((u) => {
        const a = from[u.id] ?? u;
        const turn = ((u.heading - a.heading + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;
        return [u.id, {x: a.x + (u.x - a.x) * t, y: a.y + (u.y - a.y) * t, heading: a.heading + turn * t}];
      }));
      drawnRef.current = next;
      setDrawn(next);
      if (t < 1) frame = requestAnimationFrame(animate);
    }
    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
  }, [game.battle.tick]);
  const units = Object.values(game.battle.units);
  const chosen = selected.map((id) => game.battle.units[id]).filter(Boolean);
  async function issue(kind: string, target?: string | [number, number]) {
    if (!selected.length) return;
    try { setGame(await call<CommandGame>(`/${game.id}/orders`, { ids: selected, kind, target })); setError(""); }
    catch (e) { setError((e as Error).message); }
  }
  async function control(paused?: boolean, speed?: number) {
    try { setGame(await call<CommandGame>(`/${game.id}/control`, { paused, speed })); setError(""); }
    catch (e) { setError((e as Error).message); }
  }
  function point(event: React.MouseEvent<SVGSVGElement>): [number, number] {
    const p = svg.current!.createSVGPoint(); p.x = event.clientX; p.y = event.clientY;
    const transformed = p.matrixTransform(svg.current!.getScreenCTM()!.inverse());
    return [Math.max(0, Math.min(1200, transformed.x)), Math.max(0, Math.min(800, transformed.y))];
  }
  function select(unit: Unit, event: React.MouseEvent) {
    event.stopPropagation();
    if (!unit.effective) return;
    if (unit.army !== game.human_army) { if (selected.length) void issue("ATTACK", unit.id); return; }
    setSelected((old) => event.shiftKey ? old.includes(unit.id) ? old.filter((id) => id !== unit.id) : [...old, unit.id] : [unit.id]);
  }
  function ground(event: React.MouseEvent<SVGSVGElement>) {
    if (!selected.length) return;
    if (event.button === 2 || mode !== "ATTACK") void issue(mode === "ATTACK" ? "MOVE" : mode, point(event));
  }
  async function download() {
    try {
      const record = await call<object>(`/${game.id}/replay`);
      const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify(record)], {type: "application/json"})); a.download = `echelon-command-${game.seed}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } catch (e) { setError((e as Error).message); }
  }
  return <div className="command-view">
    <div className="command-heading"><div><span className="eyebrow">COMMAND MODE · {game.battle.map.replace("_", " ").toUpperCase()}</span><h1>{game.human_army} command</h1></div><div><strong>{game.battle.time.toFixed(1)}s</strong> · Objective Blue {game.battle.objective.Blue.toFixed(0)}/35 · Red {game.battle.objective.Red.toFixed(0)}/35</div></div>
    <div className="command-controls"><button onClick={() => void control(!game.paused)}>{game.paused ? "Resume" : "Pause"}</button><label>Speed <select aria-label="Simulation speed" value={game.speed} onChange={(e) => void control(undefined, Number(e.target.value))}>{[0.5, 1, 2, 4].map((v) => <option key={v} value={v}>{v}×</option>)}</select></label><button onClick={() => setZoom((z) => Math.min(2, z + 0.2))}>Zoom +</button><button onClick={() => setZoom((z) => Math.max(1, z - 0.2))}>Zoom −</button><button onClick={onNew}>New battle</button></div>
    <div className="command-layout"><div className="command-field"><svg ref={svg} viewBox={`${600 - 600 / zoom} ${400 - 400 / zoom} ${1200 / zoom} ${800 / zoom}`} onClick={ground} onContextMenu={(e) => { e.preventDefault(); ground(e); }} aria-label="Command battlefield">
      <rect width="1200" height="800" fill="#b7aa84"/><rect x="495" y="295" width="210" height="210" rx="105" fill="#cab266" opacity=".6" stroke="#f9e2a0" strokeWidth="3"/><text x="600" y="398" textAnchor="middle" fill="#4d472d" fontSize="19">OBJECTIVE</text>
      {game.battle.map === "ridge_forest" && <><rect x="570" y="160" width="100" height="480" fill="#ae9574" opacity=".8"/><ellipse cx="420" cy="250" rx="120" ry="135" fill="#526e4f" opacity=".8"/><ellipse cx="790" cy="550" rx="120" ry="135" fill="#526e4f" opacity=".8"/></>}
      {chosen.map((u) => u.destination && <polyline key={`path-${u.id}`} points={[[u.x,u.y], ...u.waypoints, u.destination].map((p) => p.join(",")).join(" ")} fill="none" stroke="#fff2b3" strokeWidth="3" strokeDasharray="10 7"/>)}
      {units.map((u) => { const p = drawn[u.id] ?? u; return <g key={u.id} onClick={(e) => select(u, e)} style={{cursor: "pointer", opacity: u.effective ? 1 : .25}} transform={`translate(${p.x} ${p.y}) rotate(${p.heading * 180 / Math.PI})`}><circle r={u.width / 2} fill={u.army === "Blue" ? "#2e5d89" : "#a84943"} stroke={selected.includes(u.id) ? "#ffdf7a" : "#fff5d5"} strokeWidth={selected.includes(u.id) ? 5 : 2}/><path d={`M ${u.width/2} 0 l -13 -7 v 14 z`} fill="#fff5d5"/><text textAnchor="middle" dominantBaseline="middle" fill="white" fontSize="18" fontWeight="bold" transform={`rotate(${-p.heading * 180 / Math.PI})`}>{u.kind[0].toUpperCase()}</text></g>; })}
    </svg></div><aside className="command-panel"><h2>Orders</h2><p>Click a formation. Shift-click to select several. Tap or right-click ground to move; tap an enemy to attack.</p><div className="command-buttons">{(["MOVE", "ATTACK", "DEFEND"] as const).map((k) => <button className={mode === k ? "active" : ""} key={k} onClick={() => setMode(k)}>{k}</button>)}{["HOLD", "RETREAT", "STOP"].map((k) => <button key={k} disabled={!selected.length} onClick={() => void issue(k)}>{k}</button>)}</div><h3>Selected formations</h3>{chosen.length ? chosen.map((u) => <div className="command-unit" key={u.id}><strong>{u.id} · {u.kind}</strong><span>{u.order} · HP {u.health.toFixed(0)} · Morale {u.morale.toFixed(0)}</span></div>) : <p>Choose your formations on the field.</p>}<h3>Recent events</h3><div className="command-events">{game.battle.events.slice(-6).reverse().map((event, i) => <p key={`${event.tick}-${i}`}>{event.tick / 10}s · {event.unit} {event.type} {event.target}</p>)}</div></aside></div>
    {error && <p role="alert" className="form-error">{error}</p>}
    {game.battle.finished && <div className="command-victory"><h2>{game.battle.winner || "Draw"} {game.battle.winner ? "victory" : "battle"}</h2><p>Decided by {game.battle.reason?.replace("_", " ")} after {game.battle.time.toFixed(1)} seconds.</p><button onClick={() => void download()}>Download replay</button><button onClick={onNew}>New battle</button></div>}
  </div>;
}
