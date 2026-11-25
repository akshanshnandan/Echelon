"""Pygame viewer for saved Echelon snapshots; it never runs battle rules."""
import argparse
import os
from pathlib import Path

import pygame

from .replay_data import battle_stats, load_recordings, terminal_caption


WIDTH, HEIGHT = 1260, 820
BOARD_X, BOARD_Y, CELL = 54, 130, 72
PANEL_X = 664
BG = (16, 24, 35)
PANEL = (26, 39, 53)
TEXT = (233, 239, 236)
MUTED = (150, 169, 178)
GOLD = (246, 195, 99)
BLUE = (75, 159, 231)
RED = (231, 104, 97)


def color_for(army):
    return BLUE if army == "Blue" else RED


def draw_text(surface, font, value, x, y, color=TEXT):
    surface.blit(font.render(str(value), True, color), (x, y))


class ReplayViewer:
    def __init__(self, recordings):
        pygame.init()
        pygame.display.set_caption("Echelon | Battle Replay")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Segoe UI", 19)
        self.small = pygame.font.SysFont("Segoe UI", 15)
        self.tiny = pygame.font.SysFont("Segoe UI", 13)
        self.title_font = pygame.font.SysFont("Segoe UI Semibold", 34, bold=True)
        self.section_font = pygame.font.SysFont("Segoe UI Semibold", 22, bold=True)
        self.recordings = recordings
        self.battle_index = 0
        self.action_index = 0
        self.playing = False
        self.speed = 1.0
        self.elapsed = 0.0
        self.animation = 0.0
        self.show_legal = False
        self.buttons = []

    @property
    def record(self):
        return self.recordings[self.battle_index][1]

    def switch_battle(self, index):
        self.battle_index = index % len(self.recordings)
        self.action_index = 0
        self.elapsed = self.animation = 0.0
        self.playing = False

    def advance(self):
        if self.action_index < len(self.record["decisions"]):
            self.action_index += 1
            self.animation = 0.001
            self.elapsed = 0.0
        else:
            self.playing = False

    def previous(self):
        self.action_index = max(0, self.action_index - 1)
        self.animation = self.elapsed = 0.0

    def restart(self):
        self.action_index = 0
        self.animation = self.elapsed = 0.0

    def update(self, dt):
        if self.animation:
            self.animation += dt
            if self.animation >= min(0.6, 0.55 / self.speed):
                self.animation = 0.0
        elif self.playing:
            self.elapsed += dt
            if self.elapsed >= max(0.12, 0.85 / self.speed):
                self.advance()

    def snapshot(self):
        if self.action_index == 0:
            return self.record["initial"]
        return self.record["decisions"][self.action_index - 1]["after"]

    def current_step(self):
        if self.action_index == 0:
            return self.record["decisions"][0]
        return self.record["decisions"][self.action_index - 1]

    def cell_center(self, position):
        row, col = position
        return (BOARD_X + col * CELL + CELL // 2,
                BOARD_Y + row * CELL + CELL // 2)

    def button(self, label, x, y, w, key, active=False):
        rect = pygame.Rect(x, y, w, 43)
        pygame.draw.rect(self.screen, (54, 77, 91) if active else PANEL,
                         rect, border_radius=9)
        pygame.draw.rect(self.screen, GOLD if active else (76, 98, 108),
                         rect, 1, border_radius=9)
        rendered = self.small.render(label, True, TEXT)
        self.screen.blit(rendered, rendered.get_rect(center=rect.center))
        self.buttons.append((rect, key))

    def draw_board(self):
        board = pygame.Rect(BOARD_X - 5, BOARD_Y - 5, CELL * 8 + 10, CELL * 8 + 10)
        pygame.draw.rect(self.screen, (69, 93, 95), board, border_radius=10)
        for row in range(8):
            for col in range(8):
                cell = pygame.Rect(BOARD_X + col * CELL, BOARD_Y + row * CELL,
                                   CELL, CELL)
                shade = (49, 71, 69) if (row + col) % 2 else (58, 81, 76)
                pygame.draw.rect(self.screen, shade, cell)
                pygame.draw.rect(self.screen, (90, 112, 105), cell, 1)
        for i in range(8):
            draw_text(self.screen, self.small, chr(65 + i),
                      BOARD_X + i * CELL + 31, BOARD_Y - 29, MUTED)
            draw_text(self.screen, self.small, str(i + 1),
                      BOARD_X - 28, BOARD_Y + i * CELL + 25, MUTED)

        state = self.snapshot()
        step = self.current_step()
        active_id = step["unit"]
        progress = (min(1.0, self.animation / min(0.6, 0.55 / self.speed))
                    if self.animation else 1.0)
        for unit_id, unit in state["units"].items():
            before = step["before"]["units"][unit_id]["position"]
            after = step["after"]["units"][unit_id]["position"]
            if self.animation and self.action_index and unit_id == step["unit"] and before != after:
                start, end = self.cell_center(before), self.cell_center(after)
                position = (start[0] + (end[0] - start[0]) * progress,
                            start[1] + (end[1] - start[1]) * progress)
            else:
                position = self.cell_center(unit["position"])
            x, y = int(position[0]), int(position[1])
            color = color_for(unit["army"])
            if not unit["effective"]:
                color = (101, 111, 112)
            if unit_id == active_id:
                pygame.draw.circle(self.screen, GOLD, (x, y - 6), 30, 3)
            if unit["kind"] == "infantry":
                pygame.draw.rect(self.screen, color, (x - 21, y - 28, 42, 37),
                                 border_radius=6)
            elif unit["kind"] == "cavalry":
                pygame.draw.polygon(self.screen, color,
                                    [(x, y - 31), (x + 24, y + 9), (x - 24, y + 9)])
            else:
                pygame.draw.circle(self.screen, color, (x, y - 9), 23)
            label = self.small.render(unit["army"][0] + unit["kind"][0].upper(),
                                      True, (18, 28, 36))
            self.screen.blit(label, label.get_rect(center=(x, y - 10)))
            if not unit["effective"]:
                pygame.draw.line(self.screen, (224, 220, 206),
                                 (x - 16, y - 25), (x + 16, y + 5), 3)
            for offset, fraction, bar_color in ((15, unit["health"] / {"infantry": 12,
                    "cavalry": 10, "artillery": 8}[unit["kind"]], (99, 208, 139)),
                                                 (23, unit["morale"] / 100, GOLD)):
                pygame.draw.rect(self.screen, (23, 38, 43), (x - 24, y + offset, 48, 5))
                pygame.draw.rect(self.screen, bar_color,
                                 (x - 24, y + offset, round(48 * fraction), 5))

        if self.animation and self.action_index and step["action"] == "ATTACK":
            attacker = self.cell_center(step["before"]["units"][step["unit"]]["position"])
            target = self.cell_center(step["before"]["units"][step["target"]]["position"])
            pygame.draw.line(self.screen, GOLD, attacker, target, max(2, round(5 * (1-progress))))
            pygame.draw.circle(self.screen, (255, 223, 159), target,
                               round(13 + 20 * progress), 3)
        if self.animation and self.action_index and step["action"] in ("ADVANCE", "RETREAT"):
            destination = self.cell_center(step["after"]["units"][step["unit"]]["position"])
            pygame.draw.circle(self.screen, GOLD, destination, 13, 2)

    def draw_panel(self):
        pygame.draw.rect(self.screen, PANEL, (PANEL_X, 92, 555, 609), border_radius=14)
        label, record = self.recordings[self.battle_index]
        step = self.current_step()
        state = self.snapshot()
        draw_text(self.screen, self.section_font, label, PANEL_X + 22, 108)
        draw_text(self.screen, self.small,
                  f"Agent {record['agent_army']}  •  Opponent {record['opponent'].title()}",
                  PANEL_X + 22, 146, MUTED)
        draw_text(self.screen, self.small,
                  f"Seed {record['seed']}  |  First {record['first_army']}",
                  PANEL_X + 22, 169, MUTED)
        pygame.draw.line(self.screen, (69, 90, 101),
                         (PANEL_X + 20, 201), (PANEL_X + 535, 201), 1)
        count = len(record["decisions"])
        draw_text(self.screen, self.section_font,
                  f"Round {step['round']}   •   {step['army']} commander",
                  PANEL_X + 22, 215)
        draw_text(self.screen, self.font,
                  f"Action {self.action_index}/{count}: {step['unit']} {step['action']}",
                  PANEL_X + 22, 250, GOLD)
        draw_text(self.screen, self.small, step["message"], PANEL_X + 22, 282)
        if self.show_legal:
            draw_text(self.screen, self.small,
                      f"Legal: {step['legal_count']}  •  Attack options: {step['attack_opportunities']}",
                      PANEL_X + 22, 307, MUTED)
            available = step.get("legal_orders", [])
            if available:
                own = [order for order in available if order["unit"] == step["unit"]]
                shown = ", ".join(f"{o['action'].title()} {o['target'] or ''}" for o in own[:3])
                draw_text(self.screen, self.tiny, shown[:82], PANEL_X + 22, 329, MUTED)
                if len(own) > 3:
                    draw_text(self.screen, self.tiny, f"+{len(own)-3} more for this unit",
                              PANEL_X + 22, 347, MUTED)
            else:
                draw_text(self.screen, self.tiny, "Older recording: counts only",
                          PANEL_X + 22, 329, MUTED)
        pygame.draw.line(self.screen, (69, 90, 101),
                         (PANEL_X + 20, 378), (PANEL_X + 535, 378), 1)
        draw_text(self.screen, self.section_font, "Battle log", PANEL_X + 22, 390)
        recent = record["decisions"][max(0, self.action_index - 6):self.action_index]
        if not recent:
            draw_text(self.screen, self.small, "Press Space or Next to begin.",
                      PANEL_X + 22, 426, MUTED)
        for i, event in enumerate(recent):
            short = event["message"]
            if len(short) > 65:
                short = short[:62] + "..."
            draw_text(self.screen, self.small, f"R{event['round']:02}  {short}",
                      PANEL_X + 22, 425 + i * 28,
                      TEXT if i == len(recent)-1 else MUTED)
        pygame.draw.line(self.screen, (69, 90, 101),
                         (PANEL_X + 20, 600), (PANEL_X + 535, 600), 1)
        stats = battle_stats(record)
        draw_text(self.screen, self.small,
                  f"Attacks {stats['attacks']}   Holds {stats['holds']}   Retreats {stats['retreats']}",
                  PANEL_X + 22, 611)
        draw_text(self.screen, self.small,
                  f"Damage {stats['damage_dealt']}   Survivors {stats['survivors']}/3",
                  PANEL_X + 22, 639)
        if state["finished"]:
            result = terminal_caption(record, state)
            outcome_color = GOLD if state["winner"] is None else color_for(state["winner"])
        else:
            result = f"Final: {record['final']['winner'] or 'Draw'}  •  {record['final']['reason']}"
            outcome_color = MUTED
        draw_text(self.screen, self.small, result, PANEL_X + 22, 668, outcome_color)

    def draw(self):
        self.screen.fill(BG)
        draw_text(self.screen, self.title_font, "ECHELON", 54, 22)
        draw_text(self.screen, self.small, "BATTLE REPLAY  /  RECORDED SIMULATION",
                  243, 40, MUTED)
        draw_text(self.screen, self.small,
                  f"{self.battle_index+1} of {len(self.recordings)}  •  Tab switches generals",
                  PANEL_X + 20, 51, MUTED)
        self.draw_board()
        self.draw_panel()
        self.buttons.clear()
        self.button("|<  Restart", 54, 732, 117, "restart")
        self.button("<  Previous", 181, 732, 117, "previous")
        self.button("Pause" if self.playing else "Play", 308, 732, 117, "play", self.playing)
        self.button("Next  >", 435, 732, 105, "next")
        self.button("L  Legal", 550, 732, 100, "legal", self.show_legal)
        self.button("−  Slower", 664, 732, 103, "slower")
        self.button(f"{self.speed:g}x", 777, 732, 66, "speed")
        self.button("+  Faster", 853, 732, 103, "faster")
        self.button("< General", 972, 732, 116, "prev_battle")
        self.button("General >", 1098, 732, 121, "next_battle")
        pygame.display.flip()

    def command(self, command):
        if command == "play":
            self.playing = not self.playing
        elif command == "next":
            self.advance()
        elif command == "previous":
            self.previous()
        elif command == "restart":
            self.restart()
        elif command == "legal":
            self.show_legal = not self.show_legal
        elif command == "slower":
            self.speed = max(0.25, self.speed / 2)
        elif command == "faster":
            self.speed = min(8.0, self.speed * 2)
        elif command == "prev_battle":
            self.switch_battle(self.battle_index - 1)
        elif command == "next_battle":
            self.switch_battle(self.battle_index + 1)

    def run(self, screenshot: Path | None = None, action_index: int = 0,
            demo_seconds: float | None = None):
        if screenshot:
            if not 0 <= action_index <= len(self.record["decisions"]):
                raise ValueError("Screenshot action index is outside the battle")
            self.action_index = action_index
            self.draw()
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(self.screen, screenshot)
            pygame.quit()
            print(f"Saved viewer screenshot: {screenshot}")
            return
        running = True
        elapsed_demo = 0.0
        if demo_seconds is not None:
            self.playing = True
        while running:
            dt = self.clock.tick(60) / 1000
            elapsed_demo += dt
            if demo_seconds is not None and elapsed_demo >= demo_seconds:
                running = False
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_SPACE:
                        self.command("play")
                    elif event.key == pygame.K_RIGHT:
                        self.command("next")
                    elif event.key == pygame.K_LEFT:
                        self.command("previous")
                    elif event.key == pygame.K_HOME:
                        self.command("restart")
                    elif event.key == pygame.K_TAB:
                        self.command("next_battle")
                    elif event.key == pygame.K_l:
                        self.command("legal")
                    elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_UP):
                        self.command("faster")
                    elif event.key in (pygame.K_MINUS, pygame.K_DOWN):
                        self.command("slower")
                    elif pygame.K_1 <= event.key <= pygame.K_9:
                        index = event.key - pygame.K_1
                        if index < len(self.recordings):
                            self.switch_battle(index)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for rect, command in self.buttons:
                        if rect.collidepoint(event.pos):
                            self.command(command)
                            break
            self.update(dt)
            self.draw()
        pygame.quit()


def choose_files():
    from tkinter import Tk, filedialog
    root = Tk()
    root.withdraw()
    names = filedialog.askopenfilenames(title="Open Echelon battle recording",
                                         filetypes=[("JSON recordings", "*.json")])
    root.destroy()
    return [Path(name) for name in names]


def main():
    parser = argparse.ArgumentParser(description="View recorded Echelon battles")
    parser.add_argument("--file", nargs="*", type=Path,
                        help="Phase 6 battle JSON files or Phase 7 comparison bundle")
    parser.add_argument("--battle-index", type=int, default=0,
                        help="Which battle to show from an older Phase 6 array")
    parser.add_argument("--recording-index", type=int, default=0,
                        help="Which loaded general to show first (zero based)")
    parser.add_argument("--screenshot", type=Path,
                        help="Render one frame to PNG and exit, useful for validation")
    parser.add_argument("--action-index", type=int, default=0)
    parser.add_argument("--demo-seconds", type=float,
                        help="Auto-play then close; useful for a quick graphics check")
    args = parser.parse_args()
    paths = args.file or choose_files()
    if not paths:
        parser.error("Select at least one recording")
    try:
        recordings = load_recordings(paths, args.battle_index)
    except ValueError as exc:
        parser.error(str(exc))
    if (args.screenshot or args.demo_seconds) and not os.environ.get("SDL_VIDEODRIVER"):
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    if not 0 <= args.recording_index < len(recordings):
        parser.error("--recording-index is outside the loaded recordings")
    viewer = ReplayViewer(recordings)
    viewer.switch_battle(args.recording_index)
    viewer.run(args.screenshot, args.action_index, args.demo_seconds)


if __name__ == "__main__":
    main()
