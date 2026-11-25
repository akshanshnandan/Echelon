"""Run with `python -m echelon` from the project root."""
import argparse
from .engine import new_battle
from .simulation import battlefield, run_batch, run_battle, summary

def main() -> None:
    parser = argparse.ArgumentParser(description="Echelon text battle simulator")
    parser.add_argument("--battles", type=int, choices=(1, 100), default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--first", choices=("Blue", "Red", "alternate"), default="alternate")
    args = parser.parse_args()
    if args.battles == 1:
        state = run_battle(args.seed, "Blue" if args.first == "alternate" else args.first)
        print("Initial battlefield (BI infantry, BC cavalry, BA artillery; R for Red):")
        print(battlefield(new_battle(state.first_army)))
        print("\nOrders:")
        for number, event in enumerate(state.history, 1):
            print(f"{number:2}. {event}")
        print("\nFinal battlefield:")
        print(battlefield(state))
        print(summary(state))
    else:
        results, states = run_batch(args.battles, args.seed, args.first)
        print(f"{args.battles} battles, seeds {args.seed} through {args.seed + args.battles - 1}, first: {args.first}")
        print(f"Blue wins: {results['Blue']}; Red wins: {results['Red']}; Draws: {results['Draw']}")
        print(f"Time limits: {sum(s.reason == 'time limit' for s in states)}")


if __name__ == "__main__":
    main()
