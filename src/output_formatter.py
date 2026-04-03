"""
Output Formatter - Writes detected openings as JSON, markdown, and Excel spreadsheet.
"""

import json
from datetime import datetime
from collections import Counter

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from models import Opening
from config import OPENING_CATEGORIES, ISSUE_DOMAINS, DATA_DIR


def write_json(openings: list[Opening], output_path: str = None) -> str:
    """Write openings to JSON file. Returns the file path."""
    if output_path is None:
        DATA_DIR.mkdir(exist_ok=True)
        output_path = str(DATA_DIR / "openings.json")

    data = {
        "generated_at": datetime.now().isoformat(),
        "total_openings": len(openings),
        "openings": [o.to_dict() for o in openings],
    }

    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    return output_path


def write_markdown(openings: list[Opening], output_path: str = None) -> str:
    """Write openings as human-readable markdown, organized by category then issue domain.
    Returns the file path.
    """
    if output_path is None:
        DATA_DIR.mkdir(exist_ok=True)
        output_path = str(DATA_DIR / "openings.md")

    lines = []
    lines.append("# Campaign Opening Scan Results")
    lines.append(f"\n*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append(f"\n**Total openings identified: {len(openings)}**")

    # Summary stats
    lines.append("\n---")
    lines.append("\n## Summary")
    lines.append("\n### By Category")

    category_counts = Counter(o.category for o in openings)
    for cat in OPENING_CATEGORIES:
        count = category_counts.get(cat, 0)
        if count > 0:
            lines.append(f"- **{cat}**: {count}")

    lines.append("\n### By Issue Domain")
    domain_counts = Counter(o.issue_domain for o in openings)
    for domain in ISSUE_DOMAINS:
        count = domain_counts.get(domain, 0)
        if count > 0:
            lines.append(f"- **{domain}**: {count}")

    # Count uncategorized
    other_categories = sum(1 for o in openings if o.category not in OPENING_CATEGORIES)
    if other_categories:
        lines.append(f"- *(Other/uncategorized)*: {other_categories}")

    lines.append("\n### By Priority")
    priority_counts = Counter(o.priority for o in openings)
    for p in range(5, 0, -1):
        count = priority_counts.get(p, 0)
        if count > 0:
            label = {5: "Exceptional", 4: "Strong", 3: "Solid", 2: "Marginal", 1: "Weak"}[p]
            lines.append(f"- **Priority {p}** ({label}): {count}")

    # Openings organized by category
    lines.append("\n---")
    lines.append("\n## Openings by Category")

    for category in OPENING_CATEGORIES:
        cat_openings = [o for o in openings if o.category == category]
        if not cat_openings:
            continue

        lines.append(f"\n### {category} ({len(cat_openings)})")

        # Sort by priority within category
        cat_openings.sort(key=lambda o: o.priority, reverse=True)

        # Group by issue domain within category
        domain_groups = {}
        for o in cat_openings:
            domain = o.issue_domain or "Other"
            if domain not in domain_groups:
                domain_groups[domain] = []
            domain_groups[domain].append(o)

        for domain, domain_openings in domain_groups.items():
            lines.append(f"\n#### {domain}")

            for i, o in enumerate(domain_openings, 1):
                priority_marker = "!" * o.priority
                lines.append(f"\n**{i}. [{priority_marker}] {o.what_happened}**")
                lines.append(f"- **Who**: {o.who}")
                lines.append(f"- **When**: {o.when}")
                lines.append(f"- **Where**: {o.where}")
                lines.append(f"- **Replication potential**: {o.replication_potential}")
                lines.append(f"- **Campaign status**: {o.campaign_status}")
                lines.append(f"- **Time sensitivity**: {o.time_sensitivity}")
                lines.append(f"- **Why this is an opening**: {o.raw_material_note}")
                lines.append(f"- **Source**: [{o.source_name}]({o.source_url})")
                if o.additional_sources:
                    for src in o.additional_sources:
                        lines.append(f"  - Also: [{src}]({src})")

    # Any uncategorized openings
    uncategorized = [o for o in openings if o.category not in OPENING_CATEGORIES]
    if uncategorized:
        lines.append(f"\n### Other/Uncategorized ({len(uncategorized)})")
        for i, o in enumerate(uncategorized, 1):
            priority_marker = "!" * o.priority
            lines.append(f"\n**{i}. [{priority_marker}] {o.what_happened}**")
            lines.append(f"- **Category**: {o.category}")
            lines.append(f"- **Issue Domain**: {o.issue_domain}")
            lines.append(f"- **Who**: {o.who}")
            lines.append(f"- **Where**: {o.where}")
            lines.append(f"- **Replication potential**: {o.replication_potential}")
            lines.append(f"- **Why this is an opening**: {o.raw_material_note}")
            lines.append(f"- **Source**: [{o.source_name}]({o.source_url})")

    lines.append("\n---")
    lines.append(f"\n*End of scan. {len(openings)} openings identified.*")

    with open(output_path, 'w') as f:
        f.write("\n".join(lines))

    return output_path


def write_xlsx(openings: list[Opening], output_path: str = None) -> str:
    """Write openings to an Excel spreadsheet, sortable and filterable.
    Returns the file path.
    """
    if output_path is None:
        DATA_DIR.mkdir(exist_ok=True)
        output_path = str(DATA_DIR / "openings.xlsx")

    wb = Workbook()

    # --- Main "Openings" sheet ---
    ws = wb.active
    ws.title = "Openings"

    headers = [
        "Priority", "Weighted Score", "What Happened", "Replication Potential",
        "Campaign Status", "Time Sensitivity", "Why This Is an Opening",
        "Category", "Issue Domain",
        "Who", "When", "Where",
        "FB", "TV", "CR", "TW", "RP", "LGV", "Score Rationale",
        "Source", "Source URL", "Additional Sources",
    ]

    # Header styling
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill("solid", fgColor="2F5496")
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin_border = Border(
        bottom=Side(style="thin", color="CCCCCC"),
    )

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment

    # Priority color fills
    priority_fills = {
        5: PatternFill("solid", fgColor="C6EFCE"),  # green
        4: PatternFill("solid", fgColor="D9E2F3"),  # light blue
        3: PatternFill("solid", fgColor="FFF2CC"),  # light yellow
        2: PatternFill("solid", fgColor="FCE4D6"),  # light orange
        1: PatternFill("solid", fgColor="F2F2F2"),  # light gray
    }
    priority_labels = {5: "5 - Exceptional", 4: "4 - Strong", 3: "3 - Solid", 2: "2 - Marginal", 1: "1 - Weak"}

    wrap_alignment = Alignment(vertical="top", wrap_text=True)

    for row_idx, o in enumerate(openings, 2):
        additional = "; ".join(o.additional_sources) if o.additional_sources else ""

        values = [
            priority_labels.get(o.priority, str(o.priority)),
            o.weighted_score,
            o.what_happened,
            o.replication_potential,
            o.campaign_status,
            o.time_sensitivity,
            o.raw_material_note,
            o.category,
            o.issue_domain,
            o.who,
            o.when,
            o.where,
            o.score_force_balance,
            o.score_target_vulnerability,
            o.score_constraint_removability,
            o.score_timing_window,
            o.score_replication_potential,
            o.score_long_game_value,
            o.score_rationale,
            o.source_name,
            o.source_url,
            additional,
        ]

        for col, value in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=col, value=value)
            cell.alignment = wrap_alignment
            cell.border = thin_border

        # Color the priority cell
        priority_cell = ws.cell(row=row_idx, column=1)
        fill = priority_fills.get(o.priority)
        if fill:
            priority_cell.fill = fill
            ws.cell(row=row_idx, column=2).fill = fill

    # Column widths
    col_widths = {
        1: 16,   # Priority
        2: 14,   # Weighted Score
        3: 50,   # What Happened
        4: 40,   # Replication Potential
        5: 30,   # Campaign Status
        6: 25,   # Time Sensitivity
        7: 45,   # Why This Is an Opening
        8: 28,   # Category
        9: 28,   # Issue Domain
        10: 25,  # Who
        11: 16,  # When
        12: 20,  # Where
        13: 6,   # FB
        14: 6,   # TV
        15: 6,   # CR
        16: 6,   # TW
        17: 6,   # RP
        18: 6,   # LGV
        19: 40,  # Score Rationale
        20: 20,  # Source
        21: 35,  # Source URL
        22: 35,  # Additional Sources
    }
    for col, width in col_widths.items():
        ws.column_dimensions[get_column_letter(col)].width = width

    # Freeze top row and enable auto-filter
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(openings) + 1}"

    # --- Summary sheet ---
    summary = wb.create_sheet("Summary")

    summary_header_font = Font(bold=True, size=12)
    summary_subheader_font = Font(bold=True, size=11)

    summary["A1"] = "Campaign Opening Scan - Summary"
    summary["A1"].font = Font(bold=True, size=14)
    summary["A2"] = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    summary["A3"] = f"Total openings: {len(openings)}"
    summary["A3"].font = summary_header_font

    # By Category
    row = 5
    summary.cell(row=row, column=1, value="By Category").font = summary_subheader_font
    row += 1
    category_counts = Counter(o.category for o in openings)
    for cat in OPENING_CATEGORIES:
        count = category_counts.get(cat, 0)
        if count > 0:
            summary.cell(row=row, column=1, value=cat)
            summary.cell(row=row, column=2, value=count)
            row += 1

    # By Issue Domain
    row += 1
    summary.cell(row=row, column=1, value="By Issue Domain").font = summary_subheader_font
    row += 1
    domain_counts = Counter(o.issue_domain for o in openings)
    for domain in ISSUE_DOMAINS:
        count = domain_counts.get(domain, 0)
        if count > 0:
            summary.cell(row=row, column=1, value=domain)
            summary.cell(row=row, column=2, value=count)
            row += 1

    # By Priority
    row += 1
    summary.cell(row=row, column=1, value="By Priority").font = summary_subheader_font
    row += 1
    priority_counts = Counter(o.priority for o in openings)
    for p in range(5, 0, -1):
        count = priority_counts.get(p, 0)
        if count > 0:
            label = priority_labels.get(p, str(p))
            summary.cell(row=row, column=1, value=label)
            summary.cell(row=row, column=2, value=count)
            row += 1

    summary.column_dimensions['A'].width = 35
    summary.column_dimensions['B'].width = 10

    wb.save(output_path)
    return output_path


def print_summary(openings: list[Opening]) -> None:
    """Print a summary of detected openings to stdout."""
    print(f"\n{'='*60}")
    print(f"  SCAN COMPLETE: {len(openings)} campaign openings identified")
    print(f"{'='*60}")

    # By category
    print("\n  By Category:")
    category_counts = Counter(o.category for o in openings)
    for cat in OPENING_CATEGORIES:
        count = category_counts.get(cat, 0)
        if count > 0:
            print(f"    {cat}: {count}")

    # By priority
    print("\n  By Priority:")
    priority_counts = Counter(o.priority for o in openings)
    for p in range(5, 0, -1):
        count = priority_counts.get(p, 0)
        if count > 0:
            label = {5: "Exceptional", 4: "Strong", 3: "Solid", 2: "Marginal", 1: "Weak"}[p]
            print(f"    Priority {p} ({label}): {count}")

    # Top 10 openings by weighted score
    top = sorted(openings, key=lambda o: (o.weighted_score, o.priority), reverse=True)[:10]
    print(f"\n  Top 10 Openings:")
    for i, o in enumerate(top, 1):
        print(f"    {i}. [P{o.priority} | {o.weighted_score:.2f}] {o.what_happened[:80]}")
        print(f"       Category: {o.category} | Issue: {o.issue_domain}")
        print(f"       Scores: FB={o.score_force_balance} TV={o.score_target_vulnerability} CR={o.score_constraint_removability} TW={o.score_timing_window} RP={o.score_replication_potential} LGV={o.score_long_game_value}")
        if o.score_rationale:
            print(f"       Rationale: {o.score_rationale[:80]}")

    print(f"\n{'='*60}")
