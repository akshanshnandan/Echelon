import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { Battlefield } from "./Battlefield";
import { Setup } from "./Setup";
import { replaySnapshot, validateReplay } from "./replay";
import type { Config, Order, Snapshot } from "./types";

const config: Config = {
  board_size: 8,
  max_rounds: 30,
  classic_opponents: ["random", "heuristic"],
  expanded_opponents: ["balanced", "cavalry", "artillery", "infantry"],
  draft: {
    gold: 13000,
    manpower: 50,
    maximum: 4,
    minimum: 1,
    units: {
      infantry: {
        gold: 2000,
        manpower: 15,
        health: 12,
        movement: 1,
        attack_power: 4,
        attack_range: 1,
      },
      cavalry: {
        gold: 3500,
        manpower: 10,
        health: 10,
        movement: 2,
        attack_power: 5,
        attack_range: 1,
      },
      artillery: {
        gold: 4000,
        manpower: 8,
        health: 8,
        movement: 1,
        attack_power: 5,
        attack_range: 3,
      },
    },
  },
};
const state: Snapshot = {
  active_army: "Blue",
  completed_rounds: 0,
  finished: false,
  winner: null,
  reason: null,
  units: {
    "B-I": {
      army: "Blue",
      kind: "infantry",
      position: [0, 1],
      health: 12,
      morale: 100,
      effective: true,
    },
    "R-C": {
      army: "Red",
      kind: "cavalry",
      position: [2, 1],
      health: 10,
      morale: 100,
      effective: true,
    },
  },
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("army setup", () => {
  it("selects an army and updates draft counters, then reports the chosen setup", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ ai_roster: ["infantry"] }),
      })),
    );
    const start = vi.fn();
    render(<Setup config={config} onStart={start} />);
    fireEvent.click(screen.getByText("Expanded"));
    fireEvent.change(screen.getByLabelText("Your army"), {
      target: { value: "Red" },
    });
    await waitFor(() =>
      expect(
        screen.getByText("Infantry", { selector: ".ai-preview p" }),
      ).toBeTruthy(),
    );
    fireEvent.click(screen.getByLabelText("Recruit cavalry"));
    expect(
      screen.getAllByText("0", { selector: ".resource-row strong" }),
    ).toHaveLength(2);
    fireEvent.click(screen.getByText("Begin battle"));
    expect(start).toHaveBeenCalledWith(
      expect.objectContaining({
        ruleset: "Expanded",
        human_army: "Red",
        roster: ["infantry", "cavalry", "artillery", "cavalry"],
      }),
    );
  });
  it("warns when a formation exceeds the cap", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, json: async () => ({ ai_roster: [] }) })),
    );
    render(<Setup config={config} onStart={vi.fn()} />);
    fireEvent.click(screen.getByText("Expanded"));
    fireEvent.click(screen.getByLabelText("Recruit cavalry"));
    fireEvent.click(screen.getByLabelText("Recruit cavalry"));
    expect(screen.getByRole("alert").textContent).toContain("Formation limit");
  });
});

describe("battlefield", () => {
  it("highlights only orders supplied by the API and sends the exact order", () => {
    const move: Order = { unit_id: "B-I", kind: "ADVANCE", target: [1, 1] };
    const select = vi.fn(),
      order = vi.fn();
    const { rerender } = render(
      <Battlefield
        state={state}
        human="Blue"
        orders={[move]}
        selected={null}
        mode="ADVANCE"
        onSelect={select}
        onOrder={order}
      />,
    );
    fireEvent.click(screen.getByTestId("cell-0-1"));
    expect(select).toHaveBeenCalledWith("B-I");
    rerender(
      <Battlefield
        state={state}
        human="Blue"
        orders={[move]}
        selected="B-I"
        mode="ADVANCE"
        onSelect={select}
        onOrder={order}
      />,
    );
    expect(screen.getByTestId("cell-1-1").className).toContain("legal-move");
    expect(screen.getByTestId("cell-1-2").className).not.toContain(
      "legal-move",
    );
    fireEvent.click(screen.getByTestId("cell-1-1"));
    expect(order).toHaveBeenCalledWith(move);
  });
  it("renders the terminal winner and does not expose legal orders", () => {
    render(
      <Battlefield
        state={{
          ...state,
          finished: true,
          winner: "Red",
          reason: "elimination",
        }}
      />,
    );
    expect(screen.getByRole("grid")).toBeTruthy();
    expect(document.querySelectorAll(".legal").length).toBe(0);
  });
  it("marks only an engine-approved enemy as an attack target", () => {
    const attack: Order = { unit_id: "B-I", kind: "ATTACK", target: "R-C" };
    const order = vi.fn();
    render(
      <Battlefield
        state={state}
        human="Blue"
        orders={[attack]}
        selected="B-I"
        mode="ATTACK"
        onOrder={order}
      />,
    );
    expect(screen.getByTestId("cell-2-1").className).toContain("legal-attack");
    fireEvent.click(screen.getByTestId("cell-2-1"));
    expect(order).toHaveBeenCalledWith(attack);
  });
});

describe("replay snapshots", () => {
  it("steps through recorded states and rejects broken continuity", () => {
    const final = {
      ...state,
      finished: true,
      winner: "Blue" as const,
      reason: "elimination",
    };
    const record = validateReplay({
      agent_army: "Blue",
      first_army: "Blue",
      initial: state,
      final,
      decisions: [
        {
          before: state,
          after: final,
          action: "HOLD",
          unit: "B-I",
          message: "holds",
        },
      ],
    });
    expect(replaySnapshot(record, 0)).toEqual(state);
    expect(replaySnapshot(record, 1)).toEqual(final);
    expect(() => validateReplay({ ...record, initial: final })).toThrow(
      "continuity",
    );
  });
});
