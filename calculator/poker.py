# /// script
# requires-python = ">=3.12"
# dependencies = ["eval7"]
# ///
"""One-time generator for odds.json: Monte Carlo pre-flop win probability of each
of the 169 canonical hold'em starting hands, for N = 2..10. The checked-in
odds.json is fetched by the Odds tab of the app's index.html (shown in poker mode).

Two matrices are emitted:
  vsRandom : equity of each hand vs N-1 uniformly random opponents, all to showdown.
  vsFold   : equity when weak hands fold pre-flop. A player folds when their own
             hand's vs-random win% is below their fair share of the pot (1/N) — the
             cutoff is `--fold-below` * (100/N), default 1.0 (fold whenever you're
             below your fair share; the fair share IS the field's average equity, so
             this folds roughly the below-average hands). Opponents dealt such a hand
             muck, so a playing hero faces a tighter, smaller field; a hand the hero
             would fold is `null`.
The fold set is recomputed per player count (it grows as the table fills).

  { "vsRandom": { "AKs": [p2..p10], … },
    "vsFold":   { "AKs": [p2..p10], … },      # null where the hero folds
    "foldMeta": { "foldBelow": 1.0, "remaining": [r2..r10] } }   # r = live players incl. hero

  uv run poker.py [--trials 1000000] [--fold-below 1.0]
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


def combos(label):
    """Number of 2-card combos a canonical hand represents (out of 1326)."""
    return 6 if len(label) == 2 else 4 if label.endswith("s") else 12


def simulate(task):
    """Monte Carlo equity for one (hand, player count) cell.

    fold_set is None for the vs-random pass; for the vs-fold pass it is the set of
    canonical labels that muck pre-flop. A T-way tie counts as 1/T of a win; when
    every opponent folds the hero wins the pot uncontested.
    """
    import eval7

    label, c1, c2, n_players, trials, seed, fold_set = task
    if fold_set is not None and label in fold_set:
        return label, n_players, None            # hero folds this hand → no equity
    rng = random.Random(seed)
    evaluate = eval7.evaluate
    hero = [eval7.Card(c1), eval7.Card(c2)]
    # each deck entry carries its rank index (0=A best) + suit so an opponent's
    # hand can be canonicalised (to test fold membership) without hashing Cards
    deck = [
        (eval7.Card(r + s), ri, s)
        for ri, r in enumerate(RANKS) for s in "shdc" if r + s not in (c1, c2)
    ]

    n_opps = n_players - 1
    need = 5 + 2 * n_opps
    equity = 0.0
    for _ in range(trials):
        drawn = rng.sample(deck, need)
        board = [d[0] for d in drawn[:5]]
        hero_score = evaluate(hero + board)
        ties = 0
        beaten = False
        for o in range(n_opps):
            (ca, ra, sa), (cb, rb, sb) = drawn[5 + 2 * o], drawn[6 + 2 * o]
            if fold_set is not None:
                if ra == rb:
                    canon = RANKS[ra] + RANKS[ra]
                else:
                    hi, lo = (ra, rb) if ra < rb else (rb, ra)
                    canon = RANKS[hi] + RANKS[lo] + ("s" if sa == sb else "o")
                if canon in fold_set:
                    continue                      # this opponent folds pre-flop
            opp_score = evaluate([ca, cb] + board)
            if opp_score > hero_score:
                beaten = True
                break
            if opp_score == hero_score:
                ties += 1
        if not beaten:
            equity += 1.0 / (1 + ties)
    return label, n_players, round(100.0 * equity / trials, 2)


def run_pool(tasks, out, tag):
    with multiprocessing.Pool() as pool:
        for done, (label, n, pct) in enumerate(pool.imap_unordered(simulate, tasks, chunksize=4), 1):
            out[label][n - 2] = pct
            if done % 50 == 0 or done == len(tasks):
                print(f"\r{tag}: {done}/{len(tasks)} cells", end="", flush=True)
    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=1_000_000, help="deals per cell")
    parser.add_argument(
        "--fold-below", type=float, default=1.0,
        help="fold when your hand's vs-random win%% is below this fraction of the fair share (1/N); 1.0 = below fair share",
    )
    parser.add_argument("--out", default="odds.json")
    args = parser.parse_args()

    hands = canonical_hands()
    labels = [h[0] for h in hands]
    n_list = list(PLAYER_COUNTS)

    def tasks_for(fold_of):
        # fold_of: n -> fold_set (or None) for that player count
        return [
            (label, c1, c2, n, args.trials, seed, fold_of(n))
            for seed, (label, c1, c2, n) in enumerate(
                (label, c1, c2, n) for label, c1, c2 in hands for n in n_list
            )
        ]

    # Pass 1 — vs uniformly random opponents.
    vs_random = {label: [0.0] * len(n_list) for label in labels}
    run_pool(tasks_for(lambda n: None), vs_random, "vs random")

    # Fold set per player count: fold hands whose vs-random win% is below the fair
    # share (100/N). Recomputed per N, so the field tightens as it fills.
    fold_sets, remaining = {}, []
    for i, n in enumerate(n_list):
        cutoff = args.fold_below * (100.0 / n)
        fs = frozenset(l for l in labels if vs_random[l][i] < cutoff)
        fold_sets[n] = fs
        play_combos = sum(combos(l) for l in labels if l not in fs)
        remaining.append(round(1 + (n - 1) * play_combos / 1326, 3))

    # Pass 2 — vs a field that folds those hands (hero folds them too → null).
    base = len(labels) * len(n_list)               # keep seeds distinct from pass 1
    fold_tasks = [
        (t[0], t[1], t[2], t[3], t[4], base + t[5], fold_sets[t[3]])
        for t in tasks_for(lambda n: None)
    ]
    vs_fold = {label: [None] * len(n_list) for label in labels}
    run_pool(fold_tasks, vs_fold, "vs fold")

    data = {
        "vsRandom": vs_random,
        "vsFold": vs_fold,
        "foldMeta": {"foldBelow": args.fold_below, "remaining": remaining},
    }
    Path(args.out).write_text(json.dumps(data, indent=0))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
