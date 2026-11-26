export type Army = "Blue" | "Red";
export type Kind = "infantry" | "cavalry" | "artillery";
export type OrderKind = "HOLD" | "ADVANCE" | "ATTACK" | "RETREAT";
export type Order = {
  unit_id: string;
  kind: OrderKind;
  target: [number, number] | string | null;
};
export type Unit = {
  army: Army;
  kind: Kind;
  position: [number, number];
  health: number;
  morale: number;
  effective: boolean;
};
export type Snapshot = {
  units: Record<string, Unit>;
  active_army: Army;
  completed_rounds: number;
  finished: boolean;
  winner: Army | null;
  reason: string | null;
};
export type Decision = {
  round: number;
  army: Army;
  unit: string;
  action: OrderKind;
  target: [number, number] | string | null;
  damage: number;
  message: string;
  before: Snapshot;
  after: Snapshot;
};
export type Game = {
  id: string;
  ruleset: "Classic" | "Expanded";
  human_army: Army;
  opponent: string;
  first_army: Army;
  deployment: string;
  seed: number;
  round: number;
  state: Snapshot;
  legal_orders: Order[];
  history: Decision[];
  rosters: Record<Army, Kind[]> | null;
  score: Record<Army, number | number[]>;
};
export type Replay = {
  version?: number;
  ruleset?: string;
  agent_army: Army;
  opponent: string;
  seed: number;
  first_army: Army;
  initial: Snapshot;
  decisions: Decision[];
  final: Snapshot;
  outcome: string;
  classification: string;
};
export type UnitInfo = {
  gold: number;
  manpower: number;
  health: number;
  movement: number;
  attack_power: number;
  attack_range: number;
};
export type Config = {
  board_size: number;
  max_rounds: number;
  classic_opponents: string[];
  expanded_opponents: string[];
  draft: {
    gold: number;
    manpower: number;
    maximum: number;
    minimum: number;
    units: Record<Kind, UnitInfo>;
  };
};
