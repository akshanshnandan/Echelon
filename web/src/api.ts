import type { Config, Game, Kind, Order, Replay } from "./types";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch("/api" + path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({}));
    throw new Error(
      typeof problem.detail === "string"
        ? problem.detail
        : `Request failed (${response.status})`,
    );
  }
  return response.json() as Promise<T>;
}

export const getConfig = () => request<Config>("/config");
export const createGame = (setup: object) =>
  request<Game>("/games", { method: "POST", body: JSON.stringify(setup) });
export const getGame = (id: string) => request<Game>(`/games/${id}`);
export const submitOrder = (id: string, order: Order) =>
  request<Game>(`/games/${id}/orders`, {
    method: "POST",
    body: JSON.stringify(order),
  });
export const getReplay = (id: string) => request<Replay>(`/games/${id}/replay`);
export const sampleReplay = (ruleset: "classic" | "expanded") =>
  request<Replay>(`/replays/sample/${ruleset}`);
export const commandSampleReplay = () => request<unknown>("/replays/sample/command");
export const previewDraft = (
  roster: Kind[],
  doctrine: string,
  human_army: string,
  seed: number,
) =>
  request<{
    roster: Kind[];
    remaining: [number, number, number];
    ai_roster: Kind[];
  }>("/draft/preview", {
    method: "POST",
    body: JSON.stringify({ roster, doctrine, human_army, seed }),
  });
