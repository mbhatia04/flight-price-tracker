#!/usr/bin/env python3
"""Check nonstop SFO->DTW round-trip fares across a date grid via SerpApi Google Flights."""
import csv
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime

ORIGIN, DEST = "SFO", "DTW"
OUTBOUND = ["2026-11-03", "2026-11-04", "2026-11-05"]
RETURN = ["2026-11-06", "2026-11-07", "2026-11-08"]
HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "fares.csv")
RAW_DIR = os.path.join(HERE, "raw")

# Corporate TLS-inspection certs fail Python 3.13's strict X.509 checks (missing AKI).
# Keep full verification; only drop the strict-profile flag.
SSL_CTX = ssl.create_default_context()
SSL_CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT


def search(api_key, out_date, ret_date):
    params = {
        "engine": "google_flights",
        "departure_id": ORIGIN,
        "arrival_id": DEST,
        "outbound_date": out_date,
        "return_date": ret_date,
        "type": "1",      # round trip
        "stops": "1",     # nonstop only
        "currency": "USD",
        "hl": "en",
        "gl": "us",
        "api_key": api_key,
    }
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60, context=SSL_CTX) as r:
        return json.load(r)


def main():
    api_key = open(os.path.expanduser("~/.serpapi_key")).read().strip()
    os.makedirs(RAW_DIR, exist_ok=True)
    now = datetime.now().isoformat(timespec="minutes")
    rows = []
    for o in OUTBOUND:
        for r in RETURN:
            try:
                data = search(api_key, o, r)
            except Exception as e:
                print(f"{o} -> {r}: ERROR {e}", file=sys.stderr)
                continue
            if "error" in data:
                print(f"{o} -> {r}: {data['error']}", file=sys.stderr)
                continue
            with open(os.path.join(RAW_DIR, f"{now}_{o}_{r}.json"), "w") as f:
                json.dump(data, f)
            insights = data.get("price_insights", {})
            for opt in data.get("best_flights", []) + data.get("other_flights", []):
                legs = opt.get("flights", [])
                if not legs or "price" not in opt:
                    continue
                leg = legs[0]
                rows.append({
                    "checked_at": now,
                    "outbound": o,
                    "return": r,
                    "price": opt["price"],
                    "airline": leg.get("airline"),
                    "flight": leg.get("flight_number"),
                    "depart": leg.get("departure_airport", {}).get("time"),
                    "arrive": leg.get("arrival_airport", {}).get("time"),
                    "price_level": insights.get("price_level"),
                    "typical_range": "-".join(map(str, insights.get("typical_price_range", []))),
                })

    new_file = not os.path.exists(LOG)
    with open(LOG, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["checked_at"])
        if new_file:
            w.writeheader()
        w.writerows(rows)

    # Cheapest per date pair
    best = {}
    for row in rows:
        k = (row["outbound"], row["return"])
        if k not in best or row["price"] < best[k]["price"]:
            best[k] = row
    print(f"Checked {now} — cheapest nonstop round trip per date pair:\n")
    print("            " + "  ".join(f"ret {d[5:]}" for d in RETURN))
    for o in OUTBOUND:
        cells = [f"${best[(o, r)]['price']:>6}" if (o, r) in best else "    --" for r in RETURN]
        print(f"out {o[5:]}   " + "     ".join(cells))
    if best:
        b = min(best.values(), key=lambda x: x["price"])
        print(f"\nBest: ${b['price']} — out {b['outbound']} {b['airline']} {b['flight']} "
              f"({b['depart']} -> {b['arrive']}), back {b['return']}")
        print(f"Google price level: {b['price_level']}, typical range: ${b['typical_range']}")


if __name__ == "__main__":
    main()
