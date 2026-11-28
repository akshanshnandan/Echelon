import type { CommandEvent, CommandState, CommandUnit } from "./CommandBattlefield";

export type CommandReplay = {
  version: 3 | 4; ruleset: "Command"; seed: number;
  map: "open_field" | "ridge_forest"; roster: CommandUnit["kind"][];
  size?: "skirmish" | "field" | "grand"; enemy_roster?: CommandUnit["kind"][]; budget?: number; manpower?: number;
  morale_rules?: {casualty:number;cavalry:number;break_shock:number};
  human_army: "Blue" | "Red"; opponent: string;
  initial: CommandState; final: CommandState;
  commands: {tick:number; ids:string[]; kind:string; target: string | [number,number] | null}[];
  events: CommandEvent[];
  checkpoints: {tick:number; state: Omit<CommandState,"events"> & {events?:CommandEvent[]}}[];
};

function finite(value: unknown): value is number { return typeof value === "number" && Number.isFinite(value); }
function validUnit(value: unknown, width: number, height: number): value is CommandUnit {
  if (!value || typeof value !== "object") return false;
  const u = value as Partial<CommandUnit>;
  return typeof u.id === "string" && (u.army === "Blue" || u.army === "Red") &&
    ["infantry","cavalry","artillery"].includes(u.kind ?? "") &&
    finite(u.x) && finite(u.y) && finite(u.heading) && finite(u.health) && finite(u.morale) &&
    u.x >= 0 && u.x <= width && u.y >= 0 && u.y <= height &&
    typeof u.effective === "boolean" && typeof u.order === "string" &&
    (u.destination === null || (Array.isArray(u.destination) && u.destination.length === 2 && u.destination.every(finite))) &&
    Array.isArray(u.waypoints) && u.waypoints.every((p) => Array.isArray(p) && p.length === 2 && p.every(finite));
}
function validState(value: unknown, map: string, width: number, height: number, ids?: string[]): value is CommandState {
  if (!value || typeof value !== "object") return false;
  const s = value as Partial<CommandState>;
  if (!Number.isInteger(s.tick) || s.tick! < 0 || !finite(s.time) || s.map !== map || !s.units || typeof s.units !== "object" ||
      !s.objective || !finite(s.objective.Blue) || !finite(s.objective.Red) || typeof s.finished !== "boolean") return false;
  const keys = Object.keys(s.units);
  return keys.length >= 4 && keys.every((id) => validUnit(s.units![id],width,height) && s.units![id].id === id) &&
    (!ids || keys.length === ids.length && ids.every((id) => keys.includes(id)));
}

export function validateCommandReplay(value: unknown): CommandReplay {
  if (!value || typeof value !== "object") throw new Error("Replay must be a JSON object");
  const record = value as Partial<CommandReplay>;
  if (![3,4].includes(record.version ?? 0) || record.ruleset !== "Command") throw new Error("Not a supported Command replay");
  if (!finite(record.seed) || !["open_field","ridge_forest"].includes(record.map ?? "") ||
      !["Blue","Red"].includes(record.human_army ?? "") || typeof record.opponent !== "string" ||
      !Array.isArray(record.roster) || !Array.isArray(record.commands) || !Array.isArray(record.events) || !Array.isArray(record.checkpoints))
    throw new Error("Incomplete Command recording");
  const dimensions = record.version === 4 ? ({skirmish:[1200,800],field:[1400,900],grand:[1600,1000]} as const)[record.size ?? "skirmish"] : [1200,800];
  if (!dimensions || (record.version === 4 && (!record.size || !Array.isArray(record.enemy_roster) || !finite(record.budget) || !finite(record.manpower) ||
      !record.morale_rules || !finite(record.morale_rules.casualty) || !finite(record.morale_rules.cavalry) || !finite(record.morale_rules.break_shock))))
    throw new Error("Invalid Command battle size or draft");
  const [width,height] = dimensions;
  if (!validState(record.initial,record.map!,width,height) || record.initial.tick !== 0 ||
      (record.version === 4 && (record.initial.width !== width || record.initial.height !== height || record.initial.ruleset_version !== 4)))
    throw new Error("Invalid Command deployment");
  const ids = Object.keys(record.initial.units);
  if (!validState(record.final,record.map!,width,height,ids) || !record.final.finished || record.final.tick <= 0)
    throw new Error("Incomplete Command final state");
  let previous = 0;
  for (const checkpoint of record.checkpoints) {
    if (!checkpoint || !Number.isInteger(checkpoint.tick) || checkpoint.tick <= previous || checkpoint.tick > record.final.tick ||
        checkpoint.tick-previous > 100 || !validState(checkpoint.state,record.map!,width,height,ids) || checkpoint.state.tick !== checkpoint.tick)
      throw new Error("Command replay checkpoint sequence is broken");
    previous = checkpoint.tick;
  }
  if (record.final.tick-previous > 100) throw new Error("Command replay is truncated or missing checkpoints");
  let lastEvent = -1;
  for (const event of record.events) {
    if (!event || !Number.isInteger(event.tick) || event.tick < 0 || event.tick < lastEvent || event.tick > record.final.tick || typeof event.type !== "string")
      throw new Error("Command replay event sequence is broken");
    lastEvent = event.tick;
  }
  let lastCommand = -1;
  for (const command of record.commands) {
    if (!command || !Number.isInteger(command.tick) || command.tick < lastCommand || command.tick > record.final.tick ||
        !Array.isArray(command.ids) || !command.ids.length || command.ids.some((id) => !ids.includes(id)) || typeof command.kind !== "string")
      throw new Error("Command replay order sequence is broken");
    lastCommand = command.tick;
  }
  return record as CommandReplay;
}

export function commandStateAt(record: CommandReplay, tick: number): CommandState {
  const frames = [record.initial, ...record.checkpoints.map((c) => c.state), record.final];
  const bounded = Math.max(0,Math.min(record.final.tick,tick));
  let index = 0;
  while (index < frames.length-1 && frames[index+1].tick <= bounded) index++;
  const before = frames[index], after = frames[Math.min(index+1,frames.length-1)];
  if (before.tick === after.tick || bounded === before.tick) return {...before, events: []} as CommandState;
  const t = (bounded-before.tick)/(after.tick-before.tick);
  const units = Object.fromEntries(Object.entries(before.units).map(([id,u]) => {
    const next = after.units[id];
    const turn = Math.atan2(Math.sin(next.heading-u.heading),Math.cos(next.heading-u.heading));
    return [id,{...u,x:u.x+(next.x-u.x)*t,y:u.y+(next.y-u.y)*t,heading:u.heading+turn*t}];
  }));
  return {...before,tick:bounded,time:bounded/10,units,events:[]};
}
