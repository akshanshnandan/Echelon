import type { Army, Decision, Order, OrderKind, Snapshot, Unit } from "./types";

const kinds: Record<string, string> = {
  infantry: "INF",
  cavalry: "CAV",
  artillery: "ART",
};
const maxHealth: Record<string, number> = {
  infantry: 12,
  cavalry: 10,
  artillery: 8,
};

type Props = {
  state: Snapshot;
  human?: Army;
  orders?: Order[];
  selected?: string | null;
  mode?: OrderKind;
  latest?: Decision;
  onSelect?: (id: string) => void;
  onOrder?: (order: Order) => void;
};

export function Battlefield({
  state,
  human,
  orders = [],
  selected,
  mode,
  latest,
  onSelect,
  onOrder,
}: Props) {
  const byCell = new Map<string, [string, Unit]>();
  Object.entries(state.units).forEach(([id, unit]) =>
    byCell.set(unit.position.join("-"), [id, unit]),
  );
  const available = orders.filter(
    (order) => order.unit_id === selected && order.kind === mode,
  );

  function cellOrder(row: number, col: number, id?: string) {
    return available.find((order) =>
      Array.isArray(order.target)
        ? order.target[0] === row && order.target[1] === col
        : order.kind === "ATTACK" && order.target === id,
    );
  }

  function click(row: number, col: number) {
    const entry = byCell.get(`${row}-${col}`);
    const found = cellOrder(row, col, entry?.[0]);
    if (found) {
      onOrder?.(found);
      return;
    }
    if (entry && entry[1].army === human && entry[1].effective)
      onSelect?.(entry[0]);
  }

  return (
    <div className="battlefield-wrap">
      <div className="axis axis-top">
        {Array.from({ length: 8 }, (_, i) => (
          <span key={i}>{String.fromCharCode(65 + i)}</span>
        ))}
      </div>
      <div className="board-row">
        <div className="axis axis-side">
          {Array.from({ length: 8 }, (_, i) => (
            <span key={i}>{i + 1}</span>
          ))}
        </div>
        <div
          className="battlefield"
          role="grid"
          aria-label="Eight by eight battlefield"
        >
          {Array.from({ length: 64 }, (_, index) => {
            const row = Math.floor(index / 8),
              col = index % 8;
            const entry = byCell.get(`${row}-${col}`);
            const [id, unit] = entry ?? [undefined, undefined];
            const legal = cellOrder(row, col, id);
            const attack = legal?.kind === "ATTACK";
            const flash = latest?.target === id && latest?.action === "ATTACK";
            return (
              <button
                key={`${row}-${col}`}
                type="button"
                data-testid={`cell-${row}-${col}`}
                onClick={() => click(row, col)}
                className={`cell ${(row + col) % 2 ? "cell-alt" : ""} ${legal ? `legal ${attack ? "legal-attack" : "legal-move"}` : ""} ${flash ? "impact" : ""}`}
                aria-label={`${String.fromCharCode(65 + col)}${row + 1}${unit ? ` ${unit.army} ${unit.kind} ${id}` : ""}${legal ? ` legal ${legal.kind.toLowerCase()}` : ""}`}
              >
                {unit && (
                  <div
                    className={`formation ${unit.army.toLowerCase()} ${unit.kind} ${unit.effective ? "" : "routed"} ${selected === id ? "selected" : ""}`}
                    data-testid={`unit-${id}`}
                  >
                    <div className="formation-symbol">
                      <span>{kinds[unit.kind]}</span>
                    </div>
                    <div className="formation-id">{id}</div>
                    <div className="bars">
                      <i
                        style={{
                          width: `${Math.max(0, (unit.health / maxHealth[unit.kind]) * 100)}%`,
                        }}
                      />
                      <b style={{ width: `${unit.morale}%` }} />
                    </div>
                  </div>
                )}
                {!unit && legal && <span className="destination" />}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
