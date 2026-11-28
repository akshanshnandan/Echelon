import { useEffect, useRef, useState } from "react";
import { CommandBattlefield } from "./CommandBattlefield";
import type { CommandEvent, CommandState, CommandUnit } from "./CommandBattlefield";
import { track, trackCompletion, trackError } from "./analytics";

export type CommandGame = {
  id: string; ruleset: "Command"; human_army: "Blue" | "Red"; opponent: string;
  seed: number; paused: boolean; speed: number; battle: CommandState;
};

async function call<T>(path: string, body?: object): Promise<T> {
  const response = await fetch(`/api/command${path}`, body === undefined ? undefined : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({}));
    if (path && response.status === 404) throw new Error("Command session expired. Start a new battle.");
    throw new Error(typeof problem.detail === "string" ? problem.detail : "Command request failed");
  }
  return response.json();
}
export const createCommand = (setup: object) => call<CommandGame>("", setup);

type Camera = {x:number; y:number; zoom:number};
type Box = {x:number; y:number; width:number; height:number};
type Drag = {x:number; y:number; world:[number,number]; pan:boolean; moved:boolean; camera:Camera};
type Position = {x:number; y:number; heading:number};

function clampCamera(camera: Camera, width: number, height: number): Camera {
  const halfX = width / 2 / camera.zoom, halfY = height / 2 / camera.zoom;
  return { ...camera, x: Math.max(halfX, Math.min(width-halfX, camera.x)), y: Math.max(halfY, Math.min(height-halfY, camera.y)) };
}

export function CommandView({ initial, onNew, onReplay }: {
  initial: CommandGame; onNew: () => void; onReplay?: (record: unknown) => void;
}) {
  const [game, setGame] = useState(initial);
  const width = game.battle.width ?? 1200, height = game.battle.height ?? 800;
  const drawnRef = useRef<Record<string,Position>>(Object.fromEntries(Object.values(initial.battle.units).map((u) => [u.id, u])));
  const [selected, setSelected] = useState<string[]>([]);
  const [mode, setMode] = useState<"MOVE" | "ATTACK" | "DEFEND">("MOVE");
  const [camera, setCamera] = useState<Camera>({x:(initial.battle.width ?? 1200)/2,y:(initial.battle.height ?? 800)/2,zoom:1});
  const [panMode, setPanMode] = useState(false);
  const [selectionBox, setSelectionBox] = useState<Box | null>(null);
  const [error, setError] = useState("");
  const [expired, setExpired] = useState(false);
  const [tutorial, setTutorial] = useState(() => localStorage.getItem("echelon-command-tutorial") !== "done");
  const [effects, setEffects] = useState<CommandEvent[]>([]);
  const svg = useRef<SVGSVGElement>(null);
  const drag = useRef<Drag | null>(null);
  const touchPointers = useRef(new Set<number>());
  const suppressClick = useRef(false);
  const sequence = useRef(0);
  const applied = useRef(0);
  const busy = useRef(false);
  const seenEvents = useRef(new Set<string>());
  const effectTimer = useRef<number | undefined>(undefined);
  const startedAt = useRef(performance.now());
  const pollErrorReported = useRef(false);

  function apply(next: CommandGame, number: number) {
    if (number < applied.current) return;
    applied.current = number;
    setGame(next);
    if (next.battle.finished) trackCompletion(next.id, {mode:"Command",map:next.battle.map,opponent:next.opponent,
      duration_seconds:Math.round((performance.now()-startedAt.current)/1000),winner:next.battle.winner ?? "draw"});
    const fresh = next.battle.events.filter((event) => {
      const key = `${event.tick}:${event.type}:${event.unit}:${event.target}:${event.damage}`;
      if (seenEvents.current.has(key)) return false;
      seenEvents.current.add(key);
      return event.type === "hit" || event.type === "routed" || event.type === "destroyed" || event.type === "rallied";
    });
    if (fresh.length) {
      setEffects(fresh);
      window.clearTimeout(effectTimer.current);
      effectTimer.current = window.setTimeout(() => setEffects([]), 650);
    }
  }

  useEffect(() => () => window.clearTimeout(effectTimer.current), []);

  useEffect(() => {
    if (game.paused || game.battle.finished || expired) return;
    let closed = false;
    let polling = false;
    const timer = window.setInterval(() => {
      if (polling || busy.current || closed) return;
      polling = true;
      const number = ++sequence.current;
      void call<CommandGame>(`/${initial.id}`).then((next) => { if (!closed) { apply(next,number); if (number >= applied.current) setError(""); pollErrorReported.current=false; } })
        .catch((e) => { if (!closed) { setError(e.message); const missing=e.message.startsWith("Command session expired"); if (missing) setExpired(true); if (!pollErrorReported.current) {trackError("poll",missing?"expired":"network");pollErrorReported.current=true;} } })
        .finally(() => { polling = false; });
    }, 250);
    return () => { closed = true; window.clearInterval(timer); };
  }, [initial.id, game.paused, game.battle.finished, expired]);

  useEffect(() => {
    const from = drawnRef.current;
    const target = game.battle.units;
    const start = performance.now();
    const nodes = Object.fromEntries(Object.keys(target).map((id) => [id, svg.current?.querySelector<SVGGElement>(`[data-unit-id="${id}"]`)]));
    let frame = 0;
    function animate(now: number) {
      const t = Math.min(1, (now-start)/250);
      for (const u of Object.values(target)) {
        const a = from[u.id] ?? u;
        const delta = Math.atan2(Math.sin(u.heading-a.heading),Math.cos(u.heading-a.heading));
        const p = {x:a.x+(u.x-a.x)*t, y:a.y+(u.y-a.y)*t, heading:a.heading+delta*t};
        drawnRef.current[u.id] = p;
        nodes[u.id]?.setAttribute("transform",`translate(${p.x} ${p.y}) rotate(${p.heading*180/Math.PI}) scale(${game.battle.size === "grand" ? .62 : game.battle.size === "field" ? .8 : 1})`);
      }
      if (t < 1) frame = requestAnimationFrame(animate);
    }
    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
  }, [game.battle.tick]);

  useEffect(() => {
    const samples: number[] = [];
    let previous = 0, frame = 0;
    function measure(now: number) {
      if (previous) samples.push(now-previous);
      previous = now;
      if (samples.length > 180) samples.shift();
      if (samples.length >= 30) {
        const sorted = [...samples].sort((a,b) => a-b);
        (window as Window & {__echelonMetrics?: object}).__echelonMetrics = {
          fps: 1000/(samples.reduce((a,b) => a+b,0)/samples.length),
          p95FrameMs: sorted[Math.floor(sorted.length*.95)], sampleCount: samples.length,
        };
      }
      frame = requestAnimationFrame(measure);
    }
    frame = requestAnimationFrame(measure);
    return () => cancelAnimationFrame(frame);
  }, []);

  async function issue(kind: string, target?: string | [number,number]) {
    if (!selected.length || game.battle.finished || expired) return;
    busy.current = true;
    const number = ++sequence.current;
    try {
      apply(await call<CommandGame>(`/${game.id}/orders`, {ids:selected,kind,target}),number);
      setError("");
    } catch (e) { setError((e as Error).message); const missing=(e as Error).message.startsWith("Command session expired"); if (missing) setExpired(true); trackError("order",missing?"expired":"rejected"); }
    finally { busy.current = false; }
  }
  async function control(paused?: boolean, speed?: number) {
    if (expired || game.battle.finished) return;
    busy.current = true;
    const number = ++sequence.current;
    try { apply(await call<CommandGame>(`/${game.id}/control`,{paused,speed}),number); setError(""); }
    catch (e) { setError((e as Error).message); const missing=(e as Error).message.startsWith("Command session expired"); if (missing) setExpired(true); trackError("control",missing?"expired":"rejected"); }
    finally { busy.current = false; }
  }
  function world(clientX:number, clientY:number): [number,number] {
    const point = svg.current!.createSVGPoint();
    point.x = clientX; point.y = clientY;
    const result = point.matrixTransform(svg.current!.getScreenCTM()!.inverse());
    return [Math.max(0,Math.min(width,result.x)),Math.max(0,Math.min(height,result.y))];
  }
  function select(u:CommandUnit,event:React.MouseEvent<SVGGElement>) {
    if (suppressClick.current) return;
    if (!u.effective) return;
    if (u.army !== game.human_army) { if (selected.length) void issue("ATTACK",u.id); return; }
    setSelected((old) => event.shiftKey ? old.includes(u.id) ? old.filter((id) => id !== u.id) : [...old,u.id] : [u.id]);
  }
  function ground(event:React.MouseEvent<SVGSVGElement>) {
    if (suppressClick.current) { suppressClick.current = false; return; }
    if (!panMode && selected.length && (event.button === 2 || mode !== "ATTACK"))
      void issue(event.button === 2 ? "MOVE" : mode === "ATTACK" ? "MOVE" : mode,world(event.clientX,event.clientY));
  }
  function pointerDown(event:React.PointerEvent<SVGSVGElement>) {
    if (event.pointerType === "touch") {
      touchPointers.current.add(event.pointerId);
      if (touchPointers.current.size > 1) {
        drag.current = null;
        setSelectionBox(null);
        suppressClick.current = true;
        return;
      }
    }
    if (event.button === 2 || (event.target as Element).closest("[data-unit-id]")) return;
    drag.current = {x:event.clientX,y:event.clientY,world:world(event.clientX,event.clientY),pan:panMode||event.button===1,moved:false,camera};
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function pointerMove(event:React.PointerEvent<SVGSVGElement>) {
    const current = drag.current;
    if (!current) return;
    const dx = event.clientX-current.x, dy = event.clientY-current.y;
    if (Math.hypot(dx,dy) < 6 && !current.moved) return;
    current.moved = true;
    if (current.pan) {
      const bounds = svg.current!.getBoundingClientRect();
      setCamera(clampCamera({...current.camera,x:current.camera.x-dx/bounds.width*width/current.camera.zoom,y:current.camera.y-dy/bounds.height*height/current.camera.zoom},width,height));
    } else {
      const [x,y] = world(event.clientX,event.clientY);
      setSelectionBox({x:Math.min(x,current.world[0]),y:Math.min(y,current.world[1]),width:Math.abs(x-current.world[0]),height:Math.abs(y-current.world[1])});
    }
  }
  function pointerUp(event:React.PointerEvent<SVGSVGElement>) {
    if (event.pointerType === "touch") {
      touchPointers.current.delete(event.pointerId);
      if (touchPointers.current.size) return;
    }
    const current = drag.current;
    if (!current) {window.setTimeout(() => {suppressClick.current=false;},0);return;}
    drag.current = null;
    setSelectionBox(null);
    if (current.moved) {
      suppressClick.current = true;
      if (!current.pan) {
        const [x,y] = world(event.clientX,event.clientY);
        const left=Math.min(x,current.world[0]),right=Math.max(x,current.world[0]);
        const top=Math.min(y,current.world[1]),bottom=Math.max(y,current.world[1]);
        const hits = Object.values(game.battle.units).filter((u) => u.army===game.human_army&&u.effective&&u.x>=left&&u.x<=right&&u.y>=top&&u.y<=bottom).map((u) => u.id);
        setSelected((old) => event.shiftKey ? [...new Set([...old,...hits])] : hits);
      }
      window.setTimeout(() => {suppressClick.current=false;},0);
    }
  }
  function zoomBy(amount:number) { setCamera((old) => clampCamera({...old,zoom:Math.max(1,Math.min(2.4,old.zoom+amount))},width,height)); }
  async function download() {
    try {
      const record = await call<object>(`/${game.id}/replay`);
      void track("replay_downloaded", {mode:"Command",map:game.battle.map});
      const url = URL.createObjectURL(new Blob([JSON.stringify(record)],{type:"application/json"}));
      const a = document.createElement("a"); a.href=url; a.download=`echelon-command-${game.seed}.json`; a.click();
      window.setTimeout(() => URL.revokeObjectURL(url),1000);
    } catch (e) {setError((e as Error).message); const missing=(e as Error).message.startsWith("Command session expired"); if (missing) setExpired(true); trackError("replay",missing?"expired":"network");}
  }
  async function replay() {
    try {onReplay?.(await call<object>(`/${game.id}/replay`));}
    catch(e) {setError((e as Error).message); const missing=(e as Error).message.startsWith("Command session expired"); if (missing) setExpired(true); trackError("replay",missing?"expired":"network");}
  }
  const chosen = selected.map((id) => game.battle.units[id]).filter(Boolean);
  const last = game.battle.events.slice(-6).reverse();
  const commander = game.human_army;
  return <div className="command-view page-enter">
    <header className="war-header">
      <div><span className="eyebrow">COMMAND MODE / {game.battle.map === "open_field" ? "OPEN FIELD" : "RIDGE AND FOREST"}</span><h1>{commander} command</h1><p>Both armies move at once. Read the ground, then commit your formations.</p></div>
      <div className="war-clock"><span>ELAPSED</span><strong>{game.battle.time.toFixed(1)}<small>s</small></strong><span>{game.paused ? "PAUSED" : `${game.speed}× LIVE`}</span></div>
    </header>
    {tutorial && <section className="war-tutorial" aria-label="Command quick start"><strong>YOUR FIRST ORDERS</strong><span>1. Select a formation or drag a box.</span><span>2. Click ground to move, an enemy to attack.</span><span>3. Right-click to move, or choose Pan before dragging the map.</span><button onClick={() => {setTutorial(false);localStorage.setItem("echelon-command-tutorial","done");}}>Got it</button></section>}
    <div className="war-topbar"><div className="war-time-controls"><button disabled={expired || game.battle.finished} onClick={() => void control(!game.paused)} aria-label={game.paused ? "Resume" : "Pause"}>{game.paused ? "▶ Resume" : "Ⅱ Pause"}</button><label>TIME SCALE<select disabled={expired || game.battle.finished} aria-label="Simulation speed" value={game.speed} onChange={(e) => void control(undefined,Number(e.target.value))}>{[0.5,1,2,4].map((n) => <option key={n} value={n}>{n}×</option>)}</select></label></div><div className="war-camera-controls"><button className={panMode?"active":""} onClick={() => setPanMode(!panMode)} aria-pressed={panMode}>Pan</button><button aria-label="Zoom out" onClick={() => zoomBy(-.2)}>−</button><span>{Math.round(camera.zoom*100)}%</span><button aria-label="Zoom in" onClick={() => zoomBy(.2)}>+</button><button onClick={() => setCamera({x:width/2,y:height/2,zoom:1})}>Reset view</button></div></div>
    <div className="war-layout"><div className="war-field-wrap"><CommandBattlefield state={game.battle} drawn={drawnRef.current} selected={selected} camera={camera} selectionBox={selectionBox} activeEvents={effects} svgRef={svg} onUnitClick={select} onUnitKey={(u) => {if(u.army===game.human_army)setSelected([u.id]);else if(selected.length)void issue("ATTACK",u.id);}} onGroundClick={ground}
      onContextMenu={(e) => {e.preventDefault();if(!panMode&&selected.length) void issue("MOVE",world(e.clientX,e.clientY));}}
      onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={(e) => {touchPointers.current.delete(e.pointerId);drag.current=null;setSelectionBox(null);}} onWheel={(e) => {e.preventDefault();zoomBy(e.deltaY<0?.12:-.12);}} />
      <div className="war-map-foot"><span>BLUE <b>{game.battle.objective.Blue.toFixed(0)}</b> / 35</span><span>STRATEGIC GROUND</span><span>RED <b>{game.battle.objective.Red.toFixed(0)}</b> / 35</span></div></div>
      <aside className="war-side"><section className="war-orders"><span className="eyebrow">FIELD ORDERS</span><h2>Direct the line</h2><div className="war-order-grid">{(["MOVE","ATTACK","DEFEND"] as const).map((kind) => <button key={kind} className={mode===kind?"active":""} onClick={() => setMode(kind)}>{kind}</button>)}{["HOLD","RETREAT","STOP"].map((kind) => <button key={kind} disabled={!selected.length} onClick={() => void issue(kind)}>{kind}</button>)}</div><p>{mode === "ATTACK" ? "Select an enemy formation to engage." : mode === "DEFEND" ? "Choose ground to protect." : "Choose ground for selected formations."}</p></section>
      <section className="war-inspector"><span className="eyebrow">FORMATION STATUS</span>{chosen.length ? chosen.map((u) => <div key={u.id} className="war-inspector-unit"><strong>{u.id} · {u.kind}</strong><span>{u.order} · HP {u.health.toFixed(0)} · Morale {u.morale.toFixed(0)}</span><div className="inspector-bars"><i style={{width:`${u.health/(u.kind==="infantry"?100:u.kind==="cavalry"?85:65)*100}%`}}/><b style={{width:`${u.morale}%`}}/></div><small>Facing {Math.round(u.heading*180/Math.PI)}° {u.target ? `· Target ${u.target}` : ""}</small></div>) : <p>Select your troops to inspect their orders, strength, and facing.</p>}</section>
      <section className="war-dispatch"><span className="eyebrow">FIELD DISPATCHES</span><div aria-live="polite">{last.length ? last.map((event,i) => <p key={`${event.tick}-${i}`} className={event.type==="routed"||event.type==="destroyed"?"war-alert":""}><time>{(event.tick/10).toFixed(1)}s</time> {event.unit ?? "Battle"} {event.type}{event.target ? ` ${event.target}` : ""}{event.reason ? ` · ${event.reason}` : ""}</p>) : <p>The armies are deploying.</p>}</div></section></aside></div>
    <nav className="formation-bar" aria-label="Friendly formations"><button onClick={() => setSelected(Object.values(game.battle.units).filter((u) => u.army === commander && u.effective).map((u) => u.id))}>Select all</button>{Object.values(game.battle.units).filter((u) => u.army === commander).map((u) => <button key={u.id} className={selected.includes(u.id) ? "active" : ""} disabled={!u.effective} onClick={(e) => setSelected((old) => e.shiftKey ? old.includes(u.id) ? old.filter((id) => id !== u.id) : [...old,u.id] : [u.id])} aria-pressed={selected.includes(u.id)}><strong>{u.id} {u.kind.slice(0,3).toUpperCase()}</strong><small>HP {u.health.toFixed(0)} · {u.morale_state ?? (u.effective ? "steady" : "routing")} · {u.order}</small></button>)}</nav>
    {error && <p className="form-error" role="alert">{error} {expired && <button onClick={onNew}>New battle</button>}</p>}
    {game.battle.finished && <section className="war-victory" role="status"><span className="eyebrow">AFTER ACTION REPORT</span><h2>{game.battle.winner ? `${game.battle.winner} victory` : "Drawn battle"}</h2><p>{game.battle.reason?.replace("_"," ")} · {game.battle.time.toFixed(1)} seconds</p><div><button onClick={() => void replay()}>Study replay</button><button onClick={() => void download()}>Download replay</button><button onClick={onNew}>New battle</button></div></section>}
  </div>;
}
