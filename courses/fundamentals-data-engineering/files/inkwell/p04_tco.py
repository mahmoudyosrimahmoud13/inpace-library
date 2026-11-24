"""Project 4: compare the total cost of ownership (TCO) of three ways to run Inkwell's analytics.

The prices below are EXAMPLES, not real quotes. Your job in this project is to replace them with prices you look
up today on the providers' pricing pages, and to defend your choice.

TCO = direct costs (hardware, cloud bills, licences) + indirect costs (the people who keep it running).
The book's point: the indirect part is often bigger than the bill, and it's the part people forget.

Run:  python p04_tco.py
"""
MONTHS = 36
ENGINEER_HOUR = 40.0          # what one hour of a data engineer costs the company (salary + overhead)

OPTIONS = {
    "Own server (on premises)": {
        "upfront": 6000,          # buy the machine (capex)
        "monthly": 120,           # power, internet, backup disk
        "hours_per_month": 20,    # patching, backups, failed disks, upgrades
        "egress_gb": 0, "egress_per_gb": 0.0,
    },
    "Database on a cloud VM": {
        "upfront": 0,
        "monthly": 260,           # VM + disk + snapshots
        "hours_per_month": 10,    # you still patch and tune the database yourself
        "egress_gb": 200, "egress_per_gb": 0.09,   # data leaving the cloud to the office dashboard (appendix B)
    },
    "Serverless cloud warehouse": {
        "upfront": 0,
        "monthly": 180,           # storage + pay-per-query, at today's data size
        "hours_per_month": 3,     # the provider runs the servers
        "egress_gb": 200, "egress_per_gb": 0.09,
        "growth_per_month": 0.04, # the bill grows with data and queries: 4% a month
    },
}


def tco(o: dict) -> tuple[float, float, float]:
    """-> (direct cost, people cost, total) over MONTHS."""
    direct = o["upfront"]
    monthly = o["monthly"]
    for _ in range(MONTHS):
        direct += monthly + o["egress_gb"] * o["egress_per_gb"]
        monthly *= 1 + o.get("growth_per_month", 0)
    people = o["hours_per_month"] * ENGINEER_HOUR * MONTHS
    return direct, people, direct + people


if __name__ == "__main__":
    print(f"Total cost of ownership over {MONTHS} months (example prices)\n")
    print(f"{'Option':30} {'Direct':>10} {'People':>10} {'Total':>10}")
    results = {name: tco(o) for name, o in OPTIONS.items()}
    for name, (direct, people, total) in sorted(results.items(), key=lambda kv: kv[1][2]):
        print(f"{name:30} {direct:10,.0f} {people:10,.0f} {total:10,.0f}")
    cheapest = min(results, key=lambda n: results[n][2])
    print(f"\nCheapest over {MONTHS} months: {cheapest}")
    share = {n: r[1] / r[2] for n, r in results.items()}
    worst = max(share, key=share.get)
    print(f"People are {share[worst]:.0%} of the cost of '{worst}': the part a price list never shows.")
    print("\nTOCO question for your write-up: what can't the team build while it looks after its own servers?")
