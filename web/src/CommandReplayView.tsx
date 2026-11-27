import { useEffect, useRef, useState } from "react";
import { CommandBattlefield } from "./CommandBattlefield";
import { commandStateAt } from "./commandReplay";
import type { CommandReplay } from "./commandReplay";

export function CommandReplayView({record}: {record:CommandReplay}) {
  const [tick,setTick] = useState(0);
  const [playing,setPlaying] = useState(false);
  const [speed,setSpeed] = useState(1);
  const last = useRef(0);
  useEffect(() => {setTick(0);setPlaying(false);last.current=0;},[record]);
  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    function advance(now:number) {
      if (last.current) setTick((old) => {
        const next = Math.min(record.final.tick,old+(now-last.current)*speed/100);
        if (next >= record.final.tick) setPlaying(false);
        return next;
      });
      last.current=now;
      frame=requestAnimationFrame(advance);
    }
    frame=requestAnimationFrame(advance);
    return () => {cancelAnimationFrame(frame);last.current=0;};
  },[playing,speed,record]);
  const state=commandStateAt(record,tick);
  const recent=record.events.filter((e) => e.tick <= tick && e.tick >= tick-20).slice(-7).reverse();
  const final=tick>=record.final.tick;
  return <div className="command-replay">
    <div className="replay-theater"><div className="replay-theater-head"><span>COMMAND RECORDING / SEED {record.seed}</span><span>{record.map.replace("_"," ").toUpperCase()}</span></div><CommandBattlefield state={state} activeEvents={recent.filter((e)=>e.tick>=tick-5)} /><div className="war-map-foot"><span>BLUE {state.objective.Blue.toFixed(0)} / 35</span><span>RECORDED SIMULATION</span><span>RED {state.objective.Red.toFixed(0)} / 35</span></div></div>
    <aside className="command-replay-panel"><span className="eyebrow">AFTER ACTION ARCHIVE</span><h2>{final ? `${record.final.winner ?? "Draw"} ${record.final.winner ? "victory" : "battle"}` : "Battle in motion"}</h2><p>{(tick/10).toFixed(1)} / {(record.final.tick/10).toFixed(1)} seconds</p><div className="command-replay-controls"><button onClick={() => {setPlaying(false);setTick(0);}} aria-label="Restart Command replay">↺ Restart</button><button onClick={() => setPlaying(!playing)} aria-label={playing?"Pause Command replay":"Play Command replay"}>{playing?"Ⅱ Pause":"▶ Play"}</button><label>Speed<select aria-label="Command replay speed" value={speed} onChange={(e)=>setSpeed(Number(e.target.value))}>{[.5,1,2,4].map((v)=><option value={v} key={v}>{v}×</option>)}</select></label></div><input type="range" aria-label="Command replay timeline" min="0" max={record.final.tick} value={Math.round(tick)} onChange={(e)=>{setPlaying(false);setTick(Number(e.target.value));}} /><div className="replay-time-labels"><span>DEPLOYMENT</span><span>FINAL RESULT</span></div><h3>Recorded events</h3><div className="replay-events">{recent.length?recent.map((event,i)=><p key={`${event.tick}-${i}`}><time>{(event.tick/10).toFixed(1)}s</time> {event.unit ?? "Battle"} {event.type} {event.target ?? ""}</p>):<p>Scrub the timeline to inspect orders and combat.</p>}</div><p className="replay-source">Positions are interpolated between recorded checkpoints. Damage and results come from the recording.</p></aside>
  </div>;
}
