#!/usr/bin/env python3
"""
tracker.py — Application pipeline tracker.

Statuses: Evaluated → Applied → Responded → Interview → Offer | Rejected | Skipped

Usage:
  python tracker.py                            # list all applications
  python tracker.py list                       # same
  python tracker.py list --status Applied      # filter by status
  python tracker.py update "<url>" Applied     # update status
  python tracker.py stats                      # summary statistics
  python tracker.py add --url "<url>" --title "Role" --company "Co"
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

TRACKER_FILE = "applications.tsv"
VALID_STATUSES = ["Evaluated", "Applied", "Responded", "Interview", "Offer", "Rejected", "Skipped"]

HEADERS = ["#", "date", "company", "role", "score", "status", "url"]

STATUS_COLORS = {
    "Evaluated":  "\033[94m",   # blue
    "Applied":    "\033[96m",   # cyan
    "Responded":  "\033[93m",   # yellow
    "Interview":  "\033[95m",   # magenta
    "Offer":      "\033[92m",   # green
    "Rejected":   "\033[91m",   # red
    "Skipped":    "\033[90m",   # grey
}
RESET = "\033[0m"
BOLD  = "\033[1m"


def load_rows():
    if not Path(TRACKER_FILE).exists():
        return []
    rows = []
    with open(TRACKER_FILE) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            while len(parts) < 7:
                parts.append("")
            rows.append({
                "id":      parts[0],
                "date":    parts[1],
                "company": parts[2],
                "role":    parts[3],
                "score":   parts[4],
                "status":  parts[5],
                "url":     parts[6],
            })
    return rows


def save_rows(rows):
    with open(TRACKER_FILE, "w") as f:
        f.write("#\tdate\tcompany\trole\tscore\tstatus\turl\n")
        for r in rows:
            f.write("\t".join([r["id"], r["date"], r["company"], r["role"],
                               r["score"], r["status"], r["url"]]) + "\n")


def cmd_list(args):
    rows = load_rows()
    if not rows:
        print("No applications tracked yet.")
        print(f"  Run: python apply.py <job_url>  to generate materials and add to tracker.")
        return

    if args.status:
        rows = [r for r in rows if r["status"].lower() == args.status.lower()]
        if not rows:
            print(f"No applications with status '{args.status}'.")
            return

    print(f"\n{BOLD}{'#':<4} {'Date':<12} {'Company':<22} {'Role':<30} {'Score':<6} {'Status':<12} URL{RESET}")
    print("─" * 110)
    for r in rows:
        color = STATUS_COLORS.get(r["status"], "")
        score_disp = r["score"] if r["score"] else "—"
        role_disp = r["role"][:28] + ".." if len(r["role"]) > 30 else r["role"]
        co_disp   = r["company"][:20] + ".." if len(r["company"]) > 22 else r["company"]
        url_disp  = r["url"][:50] + "…" if len(r["url"]) > 51 else r["url"]
        print(f"{r['id']:<4} {r['date']:<12} {co_disp:<22} {role_disp:<30} "
              f"{score_disp:<6} {color}{r['status']:<12}{RESET} {url_disp}")
    print()


def cmd_update(args):
    url    = args.url
    status = args.new_status

    if status not in VALID_STATUSES:
        sys.exit(f"Error: invalid status '{status}'. Choose from: {', '.join(VALID_STATUSES)}")

    rows = load_rows()
    matched = False
    for r in rows:
        if r["url"] == url:
            old = r["status"]
            r["status"] = status
            matched = True
            print(f"✓ Updated #{r['id']} {r['company']} — {r['role']}")
            print(f"  {old} → {status}")
            break

    if not matched:
        sys.exit(f"Error: URL not found in tracker.\n  URL: {url}")

    save_rows(rows)


def cmd_stats(args):
    rows = load_rows()
    if not rows:
        print("No applications tracked yet.")
        return

    counts = {s: 0 for s in VALID_STATUSES}
    for r in rows:
        if r["status"] in counts:
            counts[r["status"]] += 1

    total = len(rows)
    print(f"\n{BOLD}Application Pipeline Stats{RESET}")
    print("─" * 35)
    for status in VALID_STATUSES:
        n = counts[status]
        if n == 0:
            continue
        color = STATUS_COLORS.get(status, "")
        bar   = "█" * n
        print(f"  {color}{status:<12}{RESET}  {n:>3}  {bar}")
    print("─" * 35)
    print(f"  {'Total':<12}  {total:>3}")

    # Funnel rates
    applied    = counts["Applied"] + counts["Responded"] + counts["Interview"] + counts["Offer"] + counts["Rejected"]
    responded  = counts["Responded"] + counts["Interview"] + counts["Offer"]
    interviews = counts["Interview"] + counts["Offer"]

    if applied > 0:
        print(f"\n{BOLD}Funnel{RESET}")
        print(f"  Applied → Response:  {responded}/{applied} ({100*responded//applied}%)")
        if responded > 0:
            print(f"  Response → Interview: {interviews}/{responded} ({100*interviews//responded}%)")
        if interviews > 0:
            print(f"  Interview → Offer:   {counts['Offer']}/{interviews} ({100*counts['Offer']//interviews}%)")
    print()


def cmd_add(args):
    rows = load_rows()
    url = args.url

    # Check for duplicate
    for r in rows:
        if r["url"] == url:
            print(f"Already tracked as #{r['id']} (status: {r['status']})")
            return

    next_id = len(rows) + 1
    date    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_row = {
        "id":      str(next_id),
        "date":    date,
        "company": args.company or "Unknown",
        "role":    args.title or "Unknown",
        "score":   "",
        "status":  "Evaluated",
        "url":     url,
    }

    rows.append(new_row)
    if not Path(TRACKER_FILE).exists():
        # save_rows writes the header
        pass
    save_rows(rows)
    print(f"✓ Added #{next_id} {new_row['company']} — {new_row['role']} (status: Evaluated)")


def main():
    parser = argparse.ArgumentParser(description="Application pipeline tracker")
    sub = parser.add_subparsers(dest="cmd")

    # list
    p_list = sub.add_parser("list", help="List all tracked applications")
    p_list.add_argument("--status", help="Filter by status")

    # update
    p_upd = sub.add_parser("update", help="Update application status")
    p_upd.add_argument("url",        help="Job URL")
    p_upd.add_argument("new_status", help=f"New status: {', '.join(VALID_STATUSES)}")

    # stats
    sub.add_parser("stats", help="Show funnel statistics")

    # add
    p_add = sub.add_parser("add", help="Manually add an application")
    p_add.add_argument("--url",     required=True)
    p_add.add_argument("--title",   default="")
    p_add.add_argument("--company", default="")

    args = parser.parse_args()

    if args.cmd in (None, "list"):
        if args.cmd is None:
            # default: list
            class FakeArgs:
                status = None
            cmd_list(FakeArgs())
        else:
            cmd_list(args)
    elif args.cmd == "update":
        cmd_update(args)
    elif args.cmd == "stats":
        cmd_stats(args)
    elif args.cmd == "add":
        cmd_add(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
