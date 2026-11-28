import type { MouseEvent, PointerEvent, RefObject, WheelEvent } from "react";

export type CommandUnit = {
  id: string; army: "Blue" | "Red"; kind: "infantry" | "cavalry" | "artillery";
  x: number; y: number; heading: number; health: number; morale: number;
  effective: boolean; order: string; target: string | null;
  destination: [number, number] | null; waypoints: [number, number][]; width: number;
  morale_state?: "steady" | "shaken" | "wavering" | "routing";
  ammo?: number; setup?: number; rallies?: number;
};
export type CommandState = {
  ruleset_version?: number; size?: string; width?: number; height?: number;
  tick: number; time: number; map: "open_field" | "ridge_forest";
  units: Record<string, CommandUnit>; objective: Record<"Blue" | "Red", number>;
  finished: boolean; winner: string | null; reason: string | null;
  events: CommandEvent[];
};
export type CommandEvent = {tick: number; type: string; unit?: string; target?: string; damage?: number; winner?: string; reason?: string};

const colors = {
  Blue: { cloth: "#355f77", light: "#aec5c7", edge: "#172e3f", banner: "#e1c17b" },
  Red: { cloth: "#a0483f", light: "#edc7ad", edge: "#562e31", banner: "#e4bc79" },
};

export function FormationMark({ kind, army }: {kind: CommandUnit["kind"]; army: CommandUnit["army"]}) {
  const c = colors[army];
  if (kind === "infantry") return <>
    {[-21, -7, 7, 21].map((y) => <rect key={y} x="-18" y={y - 4} width="28" height="8" rx="2" fill={c.cloth} stroke={c.edge} strokeWidth="1.5" />)}
    {[-21, -7, 7, 21].map((y) => <circle key={`h${y}`} cx="-11" cy={y} r="2.6" fill={c.light} />)}
    <path d="M 12 -27 L 31 -27 L 31 27 L 12 27" fill="none" stroke={c.banner} strokeWidth="2" />
  </>;
  if (kind === "cavalry") return <>
    {[-18, 0, 18].map((y) => <rect key={y} x="-16" y={y - 6} width="30" height="12" rx="6" fill={c.cloth} stroke={c.edge} strokeWidth="2" />)}
    {[-18, 0, 18].map((y) => <path key={`horse${y}`} d={`M 13 ${y-4} l 13 -5 4 6 -8 5 -9 3 z`} fill={c.edge} stroke={c.light} strokeWidth="1" />)}
    {[-18, 0, 18].map((y) => <circle key={`rider${y}`} cx="-5" cy={y} r="4" fill={c.banner} />)}
  </>;
  return <>
    {[-17, 17].map((y) => <rect key={y} x="-20" y={y - 5} width="29" height="10" rx="2" fill={c.cloth} stroke={c.edge} strokeWidth="2" />)}
    {[-17, 17].map((y) => <rect key={`barrel${y}`} x="5" y={y - 3} width="27" height="6" rx="2" fill="#26353a" stroke={c.banner} strokeWidth="1" />)}
    {[-17, 17].map((y) => <circle key={`wheel${y}`} cx="-9" cy={y + 8} r="5" fill="#292e2a" stroke={c.banner} strokeWidth="1.5" />)}
  </>;
}

export function UnitArtwork({kind, army}: {kind: CommandUnit["kind"]; army: CommandUnit["army"]}) {
  return <svg className="unit-artwork" viewBox="-42 -42 84 84" aria-hidden="true"><FormationMark kind={kind} army={army} /></svg>;
}

const trees = Array.from({length: 28}, (_, i) => {
  const forest = i < 14 ? [420, 250] : [790, 550];
  const n = i % 14;
  const angle = n * 2.4;
  const radius = 0.22 + (n % 4) * 0.19;
  return { x: forest[0] + Math.cos(angle) * 105 * radius,
           y: forest[1] + Math.sin(angle) * 120 * radius,
           r: 10 + n % 4 * 2 };
});

type Props = {
  state: CommandState;
  drawn?: Record<string, {x:number; y:number; heading:number}>;
  selected?: string[];
  target?: string | null;
  camera?: {x:number; y:number; zoom:number};
  selectionBox?: {x:number; y:number; width:number; height:number} | null;
  activeEvents?: CommandEvent[];
  svgRef?: RefObject<SVGSVGElement | null>;
  onUnitClick?: (unit: CommandUnit, event: MouseEvent<SVGGElement>) => void;
  onUnitKey?: (unit: CommandUnit) => void;
  onGroundClick?: (event: MouseEvent<SVGSVGElement>) => void;
  onContextMenu?: (event: MouseEvent<SVGSVGElement>) => void;
  onPointerDown?: (event: PointerEvent<SVGSVGElement>) => void;
  onPointerMove?: (event: PointerEvent<SVGSVGElement>) => void;
  onPointerUp?: (event: PointerEvent<SVGSVGElement>) => void;
  onPointerCancel?: (event: PointerEvent<SVGSVGElement>) => void;
  onWheel?: (event: WheelEvent<SVGSVGElement>) => void;
};

export function CommandBattlefield({state, drawn, selected = [], target, camera, selectionBox,
  activeEvents = [], svgRef, onUnitClick, onUnitKey, onGroundClick, onContextMenu, onPointerDown, onPointerMove, onPointerUp, onPointerCancel, onWheel}: Props) {
  const units = Object.values(state.units);
  const width = state.width ?? 1200, height = state.height ?? 800;
  const viewCamera = camera ?? {x:width/2,y:height/2,zoom:1};
  const spanX = width / viewCamera.zoom, spanY = height / viewCamera.zoom;
  const objectiveBlue = Math.min(1, state.objective.Blue / 35);
  const objectiveRed = Math.min(1, state.objective.Red / 35);
  return <svg ref={svgRef} className="war-map" viewBox={`${viewCamera.x - spanX/2} ${viewCamera.y - spanY/2} ${spanX} ${spanY}`}
    aria-label="Command battlefield" role="img" onClick={onGroundClick} onContextMenu={onContextMenu}
    onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerCancel} onWheel={onWheel}>
    <defs>
      <pattern id="field-grain" width="64" height="64" patternUnits="userSpaceOnUse"><path d="M 8 12 l 5 -2 M 32 48 l 4 1 M 53 9 l 2 -4" stroke="#6f795e" strokeWidth="1" opacity=".22" /></pattern>
      <pattern id="field-lines" width="120" height="120" patternUnits="userSpaceOnUse"><path d="M 0 0 H 120 M 0 0 V 120" fill="none" stroke="#607058" strokeWidth="1" opacity=".13" /></pattern>
    </defs>
    <rect width={width} height={height} fill="#b9ae86" />
    <rect width={width} height={height} fill="url(#field-grain)" />
    <rect width={width} height={height} fill="url(#field-lines)" />
    <g transform={`scale(${width/1200} ${height/800})`}>
    <path d="M 0 160 Q 180 120 340 165 T 690 150 T 1200 155 M 0 630 Q 260 670 490 630 T 900 645 T 1200 620" fill="none" stroke="#d9ca9c" strokeWidth="2" opacity=".5" />
    {state.map === "ridge_forest" && <>
      <rect x="570" y="160" width="100" height="480" fill="#ac9971" opacity=".76" stroke="#75654e" strokeWidth="2" />
      {[0,1,2,3,4].map((i) => <path key={`ridge${i}`} d={`M ${580+i*18} 164 Q ${565+i*18} 370 ${580+i*18} 636`} fill="none" stroke={i % 2 ? "#6f6049" : "#ead8a6"} strokeWidth="3" opacity=".48" />)}
      <ellipse cx="420" cy="250" rx="120" ry="135" fill="#687e5d" opacity=".76" stroke="#405743" strokeWidth="4" strokeDasharray="12 8" />
      <ellipse cx="790" cy="550" rx="120" ry="135" fill="#687e5d" opacity=".76" stroke="#405743" strokeWidth="4" strokeDasharray="12 8" />
      {trees.map((tree, i) => <circle key={`tree${i}`} cx={tree.x} cy={tree.y} r={tree.r} fill={i % 3 ? "#3e664d" : "#507451"} stroke="#294b3e" strokeWidth="2" opacity=".85" />)}
      <text x="620" y="179" textAnchor="middle" className="terrain-label">RIDGE</text>
      <text x="420" y="115" textAnchor="middle" className="terrain-label">FOREST</text>
      <text x="790" y="704" textAnchor="middle" className="terrain-label">FOREST</text>
    </>}
    <circle cx="600" cy="400" r="105" fill="#c4a766" fillOpacity=".19" stroke="#f5db99" strokeWidth="3" strokeDasharray="12 9" />
    <circle cx="600" cy="400" r="67" fill="none" stroke="#8b784a" strokeWidth="1.5" opacity=".65" />
    <path d="M 600 305 V 325 M 600 475 V 495 M 505 400 H 525 M 675 400 H 695" stroke="#f5db99" strokeWidth="3" />
    <text x="600" y="400" textAnchor="middle" className="objective-label">STRATEGIC GROUND</text>
    <text x="600" y="420" textAnchor="middle" className="objective-caption">HOLD 35 SECONDS</text>
    <circle cx="600" cy="400" r="85" fill="none" stroke="#326784" strokeWidth="7" strokeDasharray={`${objectiveBlue*534} 534`} transform="rotate(-90 600 400)" />
    <circle cx="600" cy="400" r="94" fill="none" stroke="#9c473f" strokeWidth="7" strokeDasharray={`${objectiveRed*591} 591`} transform="rotate(-90 600 400)" />
    </g>
    {selected.map((id) => {
      const u = state.units[id];
      if (!u) return null;
      const route = [...u.waypoints, ...(u.destination ? [u.destination] : [])];
      if (!route.length && u.order !== "ATTACK") return null;
      const end = u.order === "ATTACK" && u.target ? state.units[u.target] : null;
      const points = [[drawn?.[id]?.x ?? u.x, drawn?.[id]?.y ?? u.y], ...route, ...(end ? [[end.x,end.y]] : [])];
      return <polyline key={`path${id}`} points={points.map((p) => p.join(",")).join(" ")} fill="none" stroke="#f8ecb8" strokeWidth="3" strokeDasharray="10 8" className="order-path" />;
    })}
    {units.map((u) => {
      const p = drawn?.[u.id] ?? u;
      const active = selected.includes(u.id);
      return <g key={u.id} data-unit-id={u.id} className={`war-formation ${u.army.toLowerCase()} ${u.effective ? "" : "routed"} ${active ? "selected" : ""}`}
        role={onUnitKey ? "button" : undefined} tabIndex={onUnitKey ? 0 : undefined} aria-label={onUnitKey ? `${u.army} ${u.kind} ${u.id}, ${u.order}` : undefined}
        onKeyDown={(e) => {if (onUnitKey && (e.key === "Enter" || e.key === " ")) {e.preventDefault();onUnitKey(u);}}}
        transform={`translate(${p.x} ${p.y}) rotate(${p.heading*180/Math.PI}) scale(${state.size === "grand" ? .62 : state.size === "field" ? .8 : 1})`} onClick={(e) => {e.stopPropagation(); onUnitClick?.(u,e);}}>
        <ellipse cx="0" cy="9" rx="40" ry="37" fill="#222b24" opacity=".23" />
        {active && <rect x="-42" y="-37" width="84" height="74" rx="6" fill="none" stroke="#fff0b8" strokeWidth="3" strokeDasharray="9 5" />}
        {target === u.id && <circle r="48" fill="none" stroke="#e8b35c" strokeWidth="3" className="target-ring" />}
        <FormationMark kind={u.kind} army={u.army} />
        <line x1="-29" y1="-33" x2="-29" y2="-50" stroke="#2f3331" strokeWidth="2" />
        <path d="M -29 -50 l 19 4 -19 6 z" fill={colors[u.army].cloth} stroke={colors[u.army].banner} strokeWidth="1.5" />
        <text x="0" y="-53" transform={`rotate(${-p.heading*180/Math.PI} 0 -53)`} textAnchor="middle" className="formation-name">{u.id} · {u.kind.slice(0,3).toUpperCase()}</text>
        <rect x="-30" y="36" width="60" height="4" fill="#332f29" />
        <rect x="-30" y="36" width={Math.max(0,60*u.health/(u.kind === "infantry" ? 100 : u.kind === "cavalry" ? 85 : 65))} height="4" fill="#8fb57d" />
        <rect x="-30" y="43" width="60" height="3" fill="#332f29" />
        <rect x="-30" y="43" width={Math.max(0,60*u.morale/100)} height="3" fill={u.morale_state === "wavering" || u.morale_state === "routing" ? "#d66b55" : "#dfb96d"} />
        {(u.morale_state === "routing" || !u.effective) && <text x="0" y="-3" transform={`rotate(${-p.heading*180/Math.PI})`} textAnchor="middle" className="routed-label">{state.ruleset_version === 4 ? "ROUTING" : "ROUTED"}</text>}
        <rect x="-45" y="-42" width="90" height="96" fill="transparent" />
      </g>;
    })}
    {activeEvents.filter((e) => e.type === "hit" && e.target && state.units[e.target]).map((e,i) => {
      const u = state.units[e.target!];
      return <circle key={`hit${e.tick}-${e.target}-${i}`} cx={u.x} cy={u.y} r="24" fill="none" stroke="#f6e2a4" strokeWidth="4" className="impact-ring" />;
    })}
    {selectionBox && <rect x={selectionBox.x} y={selectionBox.y} width={selectionBox.width} height={selectionBox.height} fill="#efe1aa" fillOpacity=".18" stroke="#f8e9b3" strokeWidth="2" strokeDasharray="8 5" pointerEvents="none" />}
    <rect x="2" y="2" width={width-4} height={height-4} fill="none" stroke="#5c604a" strokeWidth="4" pointerEvents="none" />
  </svg>;
}
