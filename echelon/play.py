"""Pygame human-versus-AI interface over the unchanged Echelon engine."""
import argparse
import os
from pathlib import Path

import pygame

from .engine import score
from .live_game import LiveGame
from .model import Order, OrderType
from .recording import state_snapshot
from .replay_data import terminal_caption
from .viewer import (BG, BLUE, BOARD_X, BOARD_Y, CELL, GOLD, HEIGHT, MUTED,
                     PANEL, RED, TEXT, WIDTH, color_for, draw_text)


DEFAULT_CHECKPOINT = Path("runs/phase6_mixed_50000/checkpoints/model_76624_steps.zip")
MOVE_COLOR = (101, 224, 153)
RETREAT_COLOR = (135, 197, 248)


class LiveInterface:
    def __init__(self, game: LiveGame, save_dir: Path = Path("runs/human_games")):
        pygame.init()
        pygame.display.set_caption("Echelon | Human vs AI")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Segoe UI", 19)
        self.small = pygame.font.SysFont("Segoe UI", 15)
        self.tiny = pygame.font.SysFont("Segoe UI", 13)
        self.title_font = pygame.font.SysFont("Segoe UI Semibold", 34, bold=True)
        self.section_font = pygame.font.SysFont("Segoe UI Semibold", 22, bold=True)
        self.game = game
        self.save_dir = Path(save_dir)
        self.selected_id = None
        self.mode = OrderType.ADVANCE
        self.status = "Select one of your formations, then choose an order."
        self.buttons = []
        self.setup_open = False
        self.settings = {}

    def open_setup(self):
        self.settings = {"human_army": self.game.human_army,
                         "opponent": self.game.opponent_name,
                         "first_army": self.game.first_army,
                         "deployment": self.game.deployment,
                         "seed": self.game.seed,
                         "checkpoint": self.game.checkpoint}
        self.setup_open = True
        self.status = "Choose settings, then start a new battle."

    def start_setup(self):
        settings = dict(self.settings)
        if settings["opponent"] == "ppo" and settings["checkpoint"] is None:
            settings["checkpoint"] = DEFAULT_CHECKPOINT
        try:
            game = LiveGame(**settings)
        except (ValueError, FileNotFoundError) as exc:
            self.status = str(exc)
            return False
        self.game = game
        self.selected_id = None
        self.mode = OrderType.ADVANCE
        self.setup_open = False
        self.status = f"New {game.human_army} battle against {game.opponent_name}."
        return True

    def select(self, unit_id: str):
        unit = next((u for u in self.game.state.units if u.id == unit_id), None)
        if (unit is None or unit.army != self.game.human_army or not unit.effective
                or self.game.state.finished or
                self.game.state.active_army != self.game.human_army):
            self.status = "Select a living formation in your army."
            return False
        self.selected_id = unit_id
        self.status = (f"{unit.army} {unit.kind} selected. Press Hold to issue it."
                       if self.mode == OrderType.HOLD else
                       f"{unit.army} {unit.kind} selected. Choose an order.")
        return True

    def targets(self):
        return (self.game.human_orders(self.selected_id, self.mode)
                if self.selected_id and not self.setup_open else [])

    def set_mode(self, kind: OrderType):
        self.mode = kind
        if kind == OrderType.HOLD and self.selected_id:
            return self.issue(Order(self.selected_id, OrderType.HOLD))
        if kind == OrderType.HOLD:
            self.status = "Select a formation, then press Hold to issue its order."
            return True
        self.status = (f"{kind.value.title()}: click a highlighted "
                       + ("enemy." if kind == OrderType.ATTACK else "square."))
        return True

    def issue(self, order: Order):
        if not self.game.submit(order):
            self.status = self.game.last_error
            return False
        self.selected_id = None
        self.status = (self.game.decisions[-1]["message"] if not self.game.state.finished else
                       terminal_caption({"agent_army": self.game.human_army},
                                        state_snapshot(self.game.state)))
        return True

    def click_board(self, position):
        if self.setup_open:
            return False
        x, y = position
        if not (BOARD_X <= x < BOARD_X + 8 * CELL and
                BOARD_Y <= y < BOARD_Y + 8 * CELL):
            return False
        if self.game.state.finished:
            self.status = "Battle finished. Restart, choose a new seed, or save the replay."
            return False
        row, col = (y - BOARD_Y) // CELL, (x - BOARD_X) // CELL
        clicked = next((u for u in self.game.state.units if u.effective
                        and (u.row, u.column) == (row, col)), None)
        if clicked and clicked.army == self.game.human_army:
            return self.select(clicked.id)
        if not self.selected_id:
            self.status = "First click one of your living formations."
            return False
        if self.mode == OrderType.ATTACK and clicked is not None:
            order = Order(self.selected_id, OrderType.ATTACK, clicked.id)
        elif self.mode in (OrderType.ADVANCE, OrderType.RETREAT):
            order = Order(self.selected_id, self.mode, (row, col))
        else:
            self.status = "Choose a highlighted destination or target."
            return False
        return self.issue(order)

    def restart(self, new_seed=False):
        self.game.reset(self.game.seed + 1 if new_seed else self.game.seed)
        self.selected_id = None
        self.mode = OrderType.ADVANCE
        self.status = (f"New battle, seed {self.game.seed}." if new_seed else
                       f"Restarted seed {self.game.seed}.")

    def save(self):
        if not self.game.state.finished:
            self.status = "Finish the battle before saving a replay."
            return None
        stem = f"battle_{self.game.seed}_{self.game.human_army.lower()}_{self.game.opponent_name}"
        path = self.save_dir / f"{stem}.json"
        index = 2
        while path.exists():
            path = self.save_dir / f"{stem}_{index}.json"
            index += 1
        self.game.save(path)
        self.status = f"Saved replay: {path}"
        return path

    def button(self, label, x, y, width, command, active=False):
        rect = pygame.Rect(x, y, width, 42)
        pygame.draw.rect(self.screen, (57, 79, 93) if active else PANEL,
                         rect, border_radius=8)
        pygame.draw.rect(self.screen, GOLD if active else (74, 97, 107),
                         rect, 1, border_radius=8)
        rendered = self.small.render(label, True, TEXT)
        self.screen.blit(rendered, rendered.get_rect(center=rect.center))
        self.buttons.append((rect, command))

    def draw_board(self):
        pygame.draw.rect(self.screen, (69, 93, 95),
                         (BOARD_X - 5, BOARD_Y - 5, CELL * 8 + 10, CELL * 8 + 10),
                         border_radius=10)
        for row in range(8):
            for col in range(8):
                rect = pygame.Rect(BOARD_X + col * CELL, BOARD_Y + row * CELL, CELL, CELL)
                pygame.draw.rect(self.screen, (49, 71, 69) if (row + col) % 2 else
                                 (58, 81, 76), rect)
                pygame.draw.rect(self.screen, (90, 112, 105), rect, 1)
        for i in range(8):
            draw_text(self.screen, self.small, chr(65 + i),
                      BOARD_X + i * CELL + 31, BOARD_Y - 29, MUTED)
            draw_text(self.screen, self.small, str(i + 1),
                      BOARD_X - 28, BOARD_Y + i * CELL + 25, MUTED)

        for order in self.targets():
            if order.kind in (OrderType.ADVANCE, OrderType.RETREAT):
                row, col = order.target
                center = (BOARD_X + col * CELL + CELL // 2,
                          BOARD_Y + row * CELL + CELL // 2)
                color = MOVE_COLOR if order.kind == OrderType.ADVANCE else RETREAT_COLOR
                pygame.draw.circle(self.screen, color, center, 19, 4)
                pygame.draw.circle(self.screen, color, center, 5)
            elif order.kind == OrderType.ATTACK:
                enemy = next(u for u in self.game.state.units if u.id == order.target)
                center = (BOARD_X + enemy.column * CELL + CELL // 2,
                          BOARD_Y + enemy.row * CELL + CELL // 2)
                pygame.draw.circle(self.screen, GOLD, center, 31, 4)

        for unit in self.game.state.units:
            x = BOARD_X + unit.column * CELL + CELL // 2
            y = BOARD_Y + unit.row * CELL + CELL // 2
            color = color_for(unit.army) if unit.effective else (98, 112, 113)
            if unit.id == self.selected_id:
                pygame.draw.circle(self.screen, GOLD, (x, y - 6), 31, 3)
            if unit.kind == "infantry":
                pygame.draw.rect(self.screen, color, (x - 21, y - 28, 42, 37),
                                 border_radius=6)
            elif unit.kind == "cavalry":
                pygame.draw.polygon(self.screen, color,
                                    ((x, y - 31), (x + 24, y + 9), (x - 24, y + 9)))
            else:
                pygame.draw.circle(self.screen, color, (x, y - 9), 23)
            label = self.small.render(unit.id.replace("-", ""),
                                      True, (18, 28, 36))
            self.screen.blit(label, label.get_rect(center=(x, y - 10)))
            if not unit.effective:
                pygame.draw.line(self.screen, TEXT, (x - 16, y - 25), (x + 16, y + 5), 3)
            maximum = {"infantry": 12, "cavalry": 10, "artillery": 8}[unit.kind]
            for offset, fraction, bar_color in ((15, unit.health / maximum, (99, 208, 139)),
                                                 (23, unit.morale / 100, GOLD)):
                pygame.draw.rect(self.screen, (23, 38, 43), (x - 24, y + offset, 48, 5))
                pygame.draw.rect(self.screen, bar_color,
                                 (x - 24, y + offset, round(48 * fraction), 5))

    def draw_panel(self):
        pygame.draw.rect(self.screen, PANEL, (664, 92, 555, 609), border_radius=14)
        if self.setup_open:
            self.draw_setup()
            return
        draw_text(self.screen, self.section_font, "Command tent", 686, 105)
        draw_text(self.screen, self.small,
                  f"You: {self.game.human_army}     AI: {self.game.opponent_name.title()}",
                  686, 144)
        shown_round = (self.game.state.completed_rounds if self.game.state.finished else
                       self.game.state.completed_rounds + 1)
        active = "Battle finished" if self.game.state.finished else self.game.state.active_army
        draw_text(self.screen, self.small,
                  f"Round {shown_round} / 30     Active: {active}", 686, 169, MUTED)
        draw_text(self.screen, self.small,
                  f"Deployment: {self.game.deployment}  |  Seed: {self.game.seed}"
                  f"  |  First: {self.game.first_army}", 686, 191, MUTED)
        pygame.draw.line(self.screen, (69, 90, 101), (684, 224), (1197, 224), 1)
        draw_text(self.screen, self.section_font, "Your order", 686, 235)
        self.buttons.clear()
        names = (("1 Hold", OrderType.HOLD), ("2 Advance", OrderType.ADVANCE),
                 ("3 Attack", OrderType.ATTACK), ("4 Retreat", OrderType.RETREAT))
        for index, (label, kind) in enumerate(names):
            self.button(label, 686 + (index % 2) * 252, 278 + (index // 2) * 52,
                        239, kind.value.lower(), self.mode == kind)
        if self.selected_id:
            unit = next(u for u in self.game.state.units if u.id == self.selected_id)
            count = len(self.game.human_orders(unit.id, self.mode))
            draw_text(self.screen, self.small,
                      f"Selected: {unit.army} {unit.kind}  |  HP {unit.health}  "
                      f"Morale {unit.morale}  |  {count} {self.mode.value.lower()} options",
                      686, 390, GOLD)
        else:
            draw_text(self.screen, self.small,
                      "Click a living friendly formation to select it.", 686, 390, MUTED)
        draw_text(self.screen, self.tiny,
                  "Green circles advance. Blue circles retreat. Gold rings attack.",
                  686, 416, MUTED)
        pygame.draw.line(self.screen, (69, 90, 101), (684, 445), (1197, 445), 1)
        draw_text(self.screen, self.section_font, "Battle log", 686, 455)
        for i, step in enumerate(self.game.decisions[-5:]):
            message = step["message"]
            if len(message) > 62:
                message = message[:59] + "..."
            draw_text(self.screen, self.small, f"R{step['round']:02} {message}",
                      686, 491 + i * 27, TEXT if i == len(self.game.decisions[-5:]) - 1 else MUTED)
        if not self.game.decisions:
            draw_text(self.screen, self.small, "Orders will appear here.", 686, 494, MUTED)
        pygame.draw.line(self.screen, (69, 90, 101), (684, 637), (1197, 637), 1)
        if self.game.state.finished:
            caption = terminal_caption({"agent_army": self.game.human_army},
                                       state_snapshot(self.game.state))
            draw_text(self.screen, self.small, caption, 686, 648, GOLD)
            draw_text(self.screen, self.tiny,
                      f"Tiebreak (units, HP, morale): Blue {score(self.game.state, 'Blue')}  "
                      f"Red {score(self.game.state, 'Red')}", 686, 674, MUTED)
        else:
            draw_text(self.screen, self.small,
                      "One formation acts per turn. HOLD is immediate.", 686, 653, MUTED)

    def draw_setup(self):
        self.buttons.clear()
        draw_text(self.screen, self.section_font, "New battle setup", 686, 109)
        draw_text(self.screen, self.small, "Choose a rule set and press Start battle.",
                  686, 145, MUTED)
        options = (
            ("Your army", "human_army", ("Blue", "Red"), 186),
            ("Opponent", "opponent", ("heuristic", "random", "ppo"), 270),
            ("Deployment", "deployment", ("fixed", "random"), 354),
            ("First move", "first_army", ("Blue", "Red"), 438),
        )
        for title, field, choices, y in options:
            draw_text(self.screen, self.small, title, 686, y, MUTED)
            width = 160 if len(choices) == 3 else 239
            for index, value in enumerate(choices):
                self.button(value.title(), 686 + index * (width + 10), y + 26,
                            width, f"set:{field}:{value}", self.settings[field] == value)
        draw_text(self.screen, self.small, f"Seed: {self.settings['seed']}", 686, 542, MUTED)
        self.button("-  Seed", 840, 535, 105, "seed_down")
        self.button("+  Seed", 955, 535, 105, "seed_up")
        checkpoint = self.settings["checkpoint"] or DEFAULT_CHECKPOINT
        draw_text(self.screen, self.tiny,
                  f"PPO file: {Path(checkpoint).name}  (local checkpoint required)",
                  686, 590, MUTED)
        self.button("Browse PPO .zip", 686, 617, 180, "browse_checkpoint")
        self.button("Start battle", 897, 617, 279, "start_setup", True)

    def draw(self):
        self.screen.fill(BG)
        draw_text(self.screen, self.title_font, "ECHELON", 54, 22)
        draw_text(self.screen, self.small, "LIVE BATTLE / HUMAN VS AI", 243, 40, MUTED)
        draw_text(self.screen, self.small,
                  f"{self.game.human_army} commander   vs   "
                  f"{self.game.ai_army} {self.game.opponent_name.title()}",
                  683, 51, MUTED)
        self.draw_board()
        self.draw_panel()
        if self.setup_open:
            self.button("M  Close setup", 54, 732, 170, "close_setup")
        else:
            self.button("R  Restart", 54, 732, 125, "restart")
            self.button("N  New seed", 189, 732, 125, "new_seed")
            self.button("S  Save", 324, 732, 105, "save")
            self.button("M  Setup", 439, 732, 105, "setup")
        draw_text(self.screen, self.small, self.status[:78], 558, 744, GOLD)
        pygame.display.flip()

    def command(self, command):
        if command == "setup":
            self.open_setup()
            return
        if command == "close_setup":
            self.setup_open = False
            self.status = "Returned to the current battle."
            return
        if command == "start_setup":
            self.start_setup()
            return
        if command.startswith("set:") and self.setup_open:
            _, field, value = command.split(":", 2)
            self.settings[field] = value
            return
        if command in ("seed_down", "seed_up") and self.setup_open:
            self.settings["seed"] += -1 if command == "seed_down" else 1
            return
        if command == "browse_checkpoint" and self.setup_open:
            from tkinter import Tk, filedialog
            root = Tk()
            root.withdraw()
            chosen = filedialog.askopenfilename(title="Select MaskablePPO checkpoint",
                                                filetypes=[("Model ZIP", "*.zip")])
            root.destroy()
            if chosen:
                self.settings["checkpoint"] = Path(chosen)
            return
        if self.setup_open:
            return
        if command in ("hold", "advance", "attack", "retreat"):
            self.set_mode(OrderType(command.upper()))
        elif command == "restart":
            self.restart()
        elif command == "new_seed":
            self.restart(new_seed=True)
        elif command == "save":
            self.save()

    def handle_click(self, position):
        """Dispatch one mouse click using the buttons from the latest frame."""
        if self.click_board(position):
            return
        for rect, command in self.buttons:
            if rect.collidepoint(position):
                self.command(command)
                return

    def run(self, screenshot: Path | None = None, smoke: bool = False,
            save_record: Path | None = None):
        if smoke:
            turns = 0
            while not self.game.state.finished:
                orders = self.game.human_orders()
                order = next((o for o in orders if o.kind == OrderType.ATTACK),
                             next((o for o in orders if o.kind == OrderType.ADVANCE), orders[0]))
                if not self.game.submit(order):
                    raise RuntimeError(self.game.last_error)
                turns += 1
                self.draw()
                if turns > 30:
                    raise RuntimeError("Smoke battle did not terminate")
            if save_record:
                self.game.save(save_record)
                print(f"Saved verified smoke replay: {save_record}")
            if screenshot:
                screenshot.parent.mkdir(parents=True, exist_ok=True)
                pygame.image.save(self.screen, screenshot)
                print(f"Saved live-game screenshot: {screenshot}")
            print(f"Smoke battle: {self.game.state.winner or 'Draw'} by "
                  f"{self.game.state.reason} after {self.game.state.completed_rounds} rounds")
            pygame.quit()
            return
        if screenshot:
            candidates = [u for u in self.game.state.units
                          if u.army == self.game.human_army and u.effective]
            own = next((u for u in candidates
                        if self.game.human_orders(u.id, OrderType.ADVANCE)), candidates[0])
            self.select(own.id)
            self.draw()
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(self.screen, screenshot)
            pygame.quit()
            print(f"Saved live-game screenshot: {screenshot}")
            return
        running = True
        while running:
            self.clock.tick(60)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_m:
                        self.command("close_setup" if self.setup_open else "setup")
                    elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                        self.command(("hold", "advance", "attack", "retreat")
                                     [event.key - pygame.K_1])
                    elif event.key == pygame.K_r:
                        self.command("restart")
                    elif event.key == pygame.K_n:
                        self.command("new_seed")
                    elif event.key == pygame.K_s:
                        self.command("save")
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.handle_click(event.pos)
            self.draw()
        pygame.quit()


def main():
    parser = argparse.ArgumentParser(description="Play Echelon against a scripted or trained AI")
    parser.add_argument("--human", choices=("Blue", "Red"), default="Blue")
    parser.add_argument("--opponent", choices=("random", "heuristic", "ppo"),
                        default="heuristic")
    parser.add_argument("--checkpoint", type=Path,
                        help="MaskablePPO .zip; defaults to the local selected Phase 6 model")
    parser.add_argument("--first", choices=("Blue", "Red"), default="Blue")
    parser.add_argument("--deployment", choices=("fixed", "random"), default="fixed")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--save-dir", type=Path, default=Path("runs/human_games"))
    parser.add_argument("--screenshot", type=Path,
                        help="Save one headless frame and exit (terminal frame with --smoke)")
    parser.add_argument("--smoke", action="store_true",
                        help="Headless automated legal-order battle for validation")
    parser.add_argument("--save-record", type=Path,
                        help="Save a verified completed recording during --smoke")
    args = parser.parse_args()
    if args.smoke or args.screenshot:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    checkpoint = args.checkpoint or (DEFAULT_CHECKPOINT if args.opponent == "ppo" else None)
    try:
        game = LiveGame(args.human, args.opponent, args.first,
                        args.deployment, args.seed, checkpoint)
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))
    LiveInterface(game, args.save_dir).run(args.screenshot, args.smoke, args.save_record)


if __name__ == "__main__":
    main()
