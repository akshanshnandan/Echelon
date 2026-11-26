import { useEffect, useRef, useState } from "react";
import { commandSampleReplay } from "./api";
import { CommandBattlefield } from "./CommandBattlefield";
import { commandStateAt, validateCommandReplay } from "./commandReplay";
import type { CommandReplay } from "./commandReplay";

export function LandingBattle({onPlay}: {onPlay:()=>void}) {
  const [record,setRecord] = useState<CommandReplay | null>(null);
  const [tick,setTick] = useState(0);
  const last = useRef(0);
  useEffect(() => { let live=true; void commandSampleReplay().then((value) => {if(live)setRecord(validateCommandReplay(value));}).catch(() => {}); return () => {live=false;}; },[]);
  useEffect(() => {
    if (!record) return;
    let frame=0;
    function animate(now:number) {
      if (last.current) setTick((old) => (old+(now-last.current)/100) % record!.final.tick);
      last.current=now;
      frame=requestAnimationFrame(animate);
    }
    frame=requestAnimationFrame(animate);
    return () => {cancelAnimationFrame(frame);last.current=0;};
  },[record]);
  return <div className="landing-battle"><div className="landing-battle-top"><span>FIELD RECORD / RIDGE AND FOREST</span><span className="landing-live">● LIVE REPLAY</span></div><div className="landing-map">{record?<CommandBattlefield state={commandStateAt(record,tick)} />:<div className="landing-map-loading">Loading battlefield record…</div>}</div><div className="landing-battle-bottom"><span>{record ? `${(tick/10).toFixed(1)}s · BLUE VS RED` : "COMMAND MODE"}</span><button onClick={onPlay}>Take command ↗</button></div></div>;
}
