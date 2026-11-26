import type { Replay } from "./types";

export function validateReplay(value: unknown): Replay {
  if (!value || typeof value !== "object")
    throw new Error("Replay must be a JSON object");
  const record = value as Partial<Replay>;
  if (
    !record.initial?.units ||
    !record.final?.units ||
    !Array.isArray(record.decisions) ||
    !record.decisions.length ||
    !record.final.finished ||
    !["Blue", "Red"].includes(record.agent_army ?? "") ||
    !["Blue", "Red"].includes(record.first_army ?? "")
  )
    throw new Error("Incomplete battle recording");
  let state = record.initial;
  for (const step of record.decisions) {
    if (
      !step.before?.units ||
      !step.after?.units ||
      JSON.stringify(step.before) !== JSON.stringify(state)
    ) {
      throw new Error("Replay snapshot continuity is broken");
    }
    state = step.after;
  }
  if (JSON.stringify(state) !== JSON.stringify(record.final))
    throw new Error("Replay terminal snapshot differs");
  return record as Replay;
}

export function replaySnapshot(record: Replay, index: number) {
  return index === 0 ? record.initial : record.decisions[index - 1].after;
}
