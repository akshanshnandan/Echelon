"""Mouse-driven Classic/Expanded setup and live Expanded battles."""
import argparse
import os
from pathlib import Path

import pygame

from .doctrines import WEIGHTS, draft
from .drafting import RULES, purchase, remaining, remove
from .engine import STATS
from .expanded import strength
from .expanded_game import ExpandedGame
from .live_game import LiveGame
from .play import LiveInterface
from .viewer import BG, GOLD, MUTED, PANEL, TEXT, WIDTH, HEIGHT, draw_text


class ArmyBuilder(LiveInterface):
    def __init__(self, seed=42, roster=("infantry", "cavalry", "artillery")):
        self.seed = seed
        self.roster = tuple(roster)
        self.ruleset = "Expanded"
        self.army = "Blue"
        self.first = "Blue"
        self.doctrine = "balanced"
        self.builder_open = True
        super().__init__(ExpandedGame(self.roster, self.doctrine, self.army,
                                      self.first, self.seed))
        self.builder_open = True
        self.status = "Build your army, preview the opponent, then start."

    def open_setup(self):
        self.builder_open = True
        self.selected_id = None
        self.status = "Change your roster and start a new battle."

    def click_board(self, position):
        return False if self.builder_open else super().click_board(position)

    def command(self, command):
        if command in ("setup", "builder"):
            self.open_setup()
            return
        if self.builder_open:
            if command.startswith("mode:"):
                self.ruleset = command.split(":", 1)[1]
            elif command.startswith("army:"):
                self.army = command.split(":", 1)[1]
            elif command.startswith("first:"):
                self.first = command.split(":", 1)[1]
            elif command.startswith("doctrine:"):
                self.doctrine = command.split(":", 1)[1]
            elif command.startswith("buy:"):
                try:
                    self.roster = purchase(self.roster, command.split(":", 1)[1])
                    self.status = "Formation purchased."
                except ValueError as exc:
                    self.status = str(exc)
            elif command.startswith("remove:"):
                try:
                    self.roster = remove(self.roster, int(command.split(":", 1)[1]))
                    self.status = "Formation removed and resources refunded."
                except (ValueError, IndexError) as exc:
                    self.status = str(exc)
            elif command == "seed_up":
                self.seed += 1
            elif command == "seed_down":
                self.seed -= 1
            elif command == "start":
                try:
                    self.game = (ExpandedGame(self.roster, self.doctrine, self.army,
                                              self.first, self.seed)
                                 if self.ruleset == "Expanded" else
                                 LiveGame(self.army, "heuristic", self.first, "fixed", self.seed))
                except ValueError as exc:
                    self.status = str(exc)
                    return
                self.builder_open = False
                self.selected_id = None
                self.status = f"{self.ruleset} battle started. Select a friendly formation."
            return
        super().command(command)
        if command in ("restart", "new_seed"):
            self.seed = self.game.seed

    def draw_builder(self):
        self.screen.fill(BG)
        self.buttons.clear()
        draw_text(self.screen, self.title_font, "ECHELON  /  ARMY BUILDER", 54, 25)
        draw_text(self.screen, self.small, "Select a ruleset and prepare your formations.",
                  55, 77, MUTED)
        self.button("Classic", 54, 110, 180, "mode:Classic", self.ruleset == "Classic")
        self.button("Expanded", 244, 110, 180, "mode:Expanded", self.ruleset == "Expanded")
        self.button("Blue army", 650, 110, 170, "army:Blue", self.army == "Blue")
        self.button("Red army", 830, 110, 170, "army:Red", self.army == "Red")
        if self.ruleset == "Classic":
            draw_text(self.screen, self.section_font, "Classic research battle", 54, 190)
            draw_text(self.screen, self.font,
                      "One infantry, cavalry, and artillery per side. Heuristic opponent.",
                      54, 235, MUTED)
            draw_text(self.screen, self.font,
                      "Original 63-value observation and 396-action encoding stay unchanged.",
                      54, 268, MUTED)
        else:
            draw_text(self.screen, self.section_font, "Recruit formations", 54, 173)
            draw_text(self.screen, self.small,
                      "Gold / manpower / movement / power / range / health", 54, 207, MUTED)
            for index, kind in enumerate(RULES.costs):
                x = 54 + index * 397
                gold, manpower = RULES.costs[kind]
                health, movement, power, attack_range = STATS[kind]
                pygame.draw.rect(self.screen, PANEL, (x, 240, 375, 148), border_radius=13)
                draw_text(self.screen, self.section_font, kind.title(), x + 20, 254)
                draw_text(self.screen, self.small,
                          f"{gold:,} gold  |  {manpower} manpower", x + 20, 291, GOLD)
                draw_text(self.screen, self.small,
                          f"HP {health}  Move {movement}  Power {power}  Range {attack_range}",
                          x + 20, 317, MUTED)
                self.button(f"+ Recruit {kind}", x + 20, 339, 335, f"buy:{kind}")
            gold_left, people_left, slots_left = remaining(self.roster)
            draw_text(self.screen, self.section_font,
                      f"Your army: {len(self.roster)}/{RULES.maximum} formations", 54, 412)
            draw_text(self.screen, self.font,
                      f"Gold remaining {gold_left:,} / {RULES.gold:,}    "
                      f"Manpower {people_left} / {RULES.manpower}    Slots {slots_left}",
                      54, 446, GOLD)
            for index, kind in enumerate(self.roster):
                x = 54 + index * 297
                pygame.draw.rect(self.screen, PANEL, (x, 480, 280, 94), border_radius=10)
                draw_text(self.screen, self.font, f"{index + 1}. {kind.title()}", x + 13, 492)
                self.button("Remove", x + 12, 523, 250, f"remove:{index}")
            draw_text(self.screen, self.section_font, "Opponent doctrine", 54, 601)
            for index, doctrine in enumerate(WEIGHTS):
                self.button(doctrine.title(), 54 + index * 240, 637, 226,
                            f"doctrine:{doctrine}", self.doctrine == doctrine)
            enemy_roster = draft(self.doctrine, f"{self.seed}:draft:"
                                 f"{'Red' if self.army == 'Blue' else 'Blue'}")
            draw_text(self.screen, self.small,
                      "AI preview: " + ", ".join(enemy_roster), 54, 692, MUTED)
        draw_text(self.screen, self.small, "First move", 1030, 78, MUTED)
        self.button("Blue first", 1010, 110, 100, "first:Blue", self.first == "Blue")
        self.button("Red first", 1120, 110, 100, "first:Red", self.first == "Red")
        draw_text(self.screen, self.small, f"Seed {self.seed}", 1005, 602, MUTED)
        self.button("-", 1004, 635, 60, "seed_down")
        self.button("+", 1074, 635, 60, "seed_up")
        self.button("Start Battle", 966, 720, 254, "start", True)
        draw_text(self.screen, self.small, self.status[:90], 54, 736, GOLD)
        pygame.display.flip()

    def draw_panel(self):
        super().draw_panel()
        if isinstance(self.game, ExpandedGame) and self.game.state.finished:
            pygame.draw.rect(self.screen, PANEL, (682, 666, 520, 30))
            draw_text(self.screen, self.tiny,
                      f"Remaining strength: Blue {float(strength(self.game.state, 'Blue')):.0f}  "
                      f"Red {float(strength(self.game.state, 'Red')):.0f}",
                      686, 674, MUTED)

    def draw(self):
        if self.builder_open:
            self.draw_builder()
        else:
            super().draw()

    def save_builder_screenshot(self, path):
        self.draw_builder()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(self.screen, path)
        pygame.quit()
        print(f"Saved army builder screenshot: {path}")


def main():
    parser = argparse.ArgumentParser(description="Build and command a custom Echelon army")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--roster", nargs="+", choices=tuple(RULES.costs),
                        default=["infantry", "cavalry", "artillery"])
    parser.add_argument("--screenshot-builder", type=Path)
    parser.add_argument("--screenshot-battle", type=Path)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--save-record", type=Path)
    args = parser.parse_args()
    if args.screenshot_builder or args.screenshot_battle or args.smoke:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    try:
        app = ArmyBuilder(args.seed, args.roster)
    except ValueError as exc:
        parser.error(str(exc))
    if args.screenshot_builder:
        app.save_builder_screenshot(args.screenshot_builder)
    elif args.screenshot_battle:
        app.command("start")
        app.run(screenshot=args.screenshot_battle)
    elif args.smoke:
        app.command("start")
        app.run(smoke=True, save_record=args.save_record)
    else:
        app.run()


if __name__ == "__main__":
    main()
