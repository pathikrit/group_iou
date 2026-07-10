# /// script
# requires-python = ">=3.12"
# dependencies = ["eval7"]
# ///
"""One-time generator for odds.json: Monte Carlo pre-flop win probability of
each of the 169 canonical hold'em starting hands vs N-1 random opponents,
for N = 2..10. The checked-in odds.json is fetched by the Odds tab of the
app's index.html (the tab is shown in poker mode).

  uv run poker.py [--trials 1000000]
"""

import argparse
import json
import multiprocessing
import random
from pathlib import Path

RANKS = "AKQJT98765432"
PLAYER_COUNTS = range(2, 11)


def canonical_hands():
    """The 169 canonical starting hands with one representative combo each.

    Equity vs random opponents is suit-symmetric, so a single combo per
    canonical hand is exact (up to Monte Carlo noise).
    """
    hands = []
    for i, r1 in enumerate(RANKS):
        for j, r2 in enumerate(RANKS):
            if i == j:
                hands.append((r1 + r2, r1 + "s", r2 + "h"))
            elif i < j:
                hands.append((r1 + r2 + "s", r1 + "s", r2 + "s"))
            elif i > j:
                hands.append((r2 + r1 + "o", r2 + "s", r1 + "h"))
    assert len(hands) == 169
    return hands


def simulate(task):
    """Monte Carlo equity for one (hand, player count) cell.

    Equity counts a T-way tie as 1/T of a win.
    """
    import eval7

    label, c1, c2, n_players, trials, seed = task
    rng = random.Random(seed)
    evaluate = eval7.evaluate
    hero = [eval7.Card(c1), eval7.Card(c2)]
    deck = [eval7.Card(r + s) for r in RANKS for s in "shdc" if r + s not in (c1, c2)]
    n_opps = n_players - 1
    need = 5 + 2 * n_opps

    equity = 0.0
    for _ in range(trials):
        drawn = rng.sample(deck, need)
        board = drawn[:5]
        hero_score = evaluate(hero + board)
        ties = 0
        beaten = False
        for o in range(n_opps):
            opp_score = evaluate(drawn[5 + 2 * o : 7 + 2 * o] + board)
            if opp_score > hero_score:
                beaten = True
                break
            if opp_score == hero_score:
                ties += 1
        if not beaten:
            equity += 1.0 / (1 + ties)
    return label, n_players, round(100.0 * equity / trials, 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=1_000_000, help="deals per cell")
    parser.add_argument("--out", default="odds.json")
    args = parser.parse_args()

    tasks = [
        (label, c1, c2, n, args.trials, seed)
        for seed, (label, c1, c2, n) in enumerate(
            (label, c1, c2, n) for label, c1, c2 in canonical_hands() for n in PLAYER_COUNTS
        )
    ]
    odds = {label: [0.0] * len(PLAYER_COUNTS) for label, _, _ in canonical_hands()}
    with multiprocessing.Pool() as pool:
        for done, (label, n, pct) in enumerate(pool.imap_unordered(simulate, tasks, chunksize=4), 1):
            odds[label][n - 2] = pct
            if done % 50 == 0 or done == len(tasks):
                print(f"\r{done}/{len(tasks)} cells", end="", flush=True)
    print()
    Path(args.out).write_text(json.dumps(odds, indent=0))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
