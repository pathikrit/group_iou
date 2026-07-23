# Regenerates odds.json (~30 min: 1M Monte Carlo deals per cell, all CPU cores,
# two passes — vs random opponents and vs a field that folds weak hands).
# odds.json is checked in; index.html (the Odds tab) fetches it at runtime.
# Retune the fold cutoff with e.g. `uv run poker.py --fold-below 0.6`.
odds:
	uv run poker.py
