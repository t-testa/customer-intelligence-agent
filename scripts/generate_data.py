"""Reproducible synthetic fixture generation; no external/customer source material."""

import csv
import json
from datetime import date, timedelta

from src.config import ROOT

ANCHOR = date(2026, 9, 16)


def main():
    directory = ROOT / "data"
    directory.mkdir(exist_ok=True)
    notes_dir = directory / "customer_notes"
    notes_dir.mkdir(exist_ok=True)
    industries = ["Software", "Healthcare", "Manufacturing", "Retail", "Education", "Logistics"]
    prefixes = ["Cedar", "Amber", "Harbor", "Maple", "Orion", "Willow", "Quartz", "Meadow"]
    suffixes = ["Works", "Labs", "Systems", "Collective", "Partners"]
    records = []
    for i in range(1, 41):
        high = i % 5 == 3
        records.append(
            dict(
                customer_id=i,
                company=f"{prefixes[(i - 1) % 8]} {suffixes[(i - 1) // 8]} (Synthetic)",
                industry=industries[(i - 1) % 6],
                monthly_revenue=f"{1200 + (i * 1379) % 24000}.00",
                contract_end=(
                    ANCHOR + timedelta(days=20 if high else (i * 17) % 300 + 61)
                ).isoformat(),
                support_tickets=8 if high else i % 7,
                nps_score=15 if high else 25 + (i * 11) % 70,
                last_contact=(ANCHOR - timedelta(days=55 if high else (i * 7) % 55)).isoformat(),
            )
        )
        entries = [
            (
                "renewal",
                "Renewal discussion: procurement needs a written success plan and an executive sponsor meeting before the contract review."
                if high
                else "Renewal discussion: sponsor confirmed satisfaction and requested next quarter planning.",
            ),
            (
                "support",
                "Implementation concerns: unresolved data import defects are blocking adoption. Support escalations remain open and the executive sponsor is concerned."
                if high
                else "Support summary: onboarding completed successfully. The team praised responsive support and stable integrations.",
            ),
            (
                "expansion",
                "Expansion opportunity: analytics seats could grow once adoption milestones are met. Account manager will validate budget; no purchase commitment exists.",
            ),
        ]
        notes = [
            dict(
                note_id=f"C{i:03d}-{kind}",
                customer_id=i,
                kind=kind,
                recorded_at=ANCHOR.isoformat(),
                text=text,
                synthetic=True,
            )
            for kind, text in entries
        ]
        (notes_dir / f"customer_{i:03d}.json").write_text(
            json.dumps(notes, indent=2) + "\n", encoding="utf-8"
        )
    with (directory / "customers.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    (directory / "README.md").write_text(
        "# Synthetic data\n\n40 fictional customers and 120 fictional notes. No real customer data. Dates are anchored to 2026-09-16; set BUSINESS_DATE for a repeatable demo or regenerate deliberately. Currency: CAD. NPS is a synthetic account-level proxy, not a statistically estimated survey NPS. Revenue is monthly recurring revenue. Tickets represent currently open tickets.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
