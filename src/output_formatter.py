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

    scored = [o for o in openings if not o.is_watch_list]
    watch_list = [o for o in openings if o.is_watch_list]

    lines.append(f"\n**Scored openings: {len(scored)} | Watch list: {len(watch_list)}**")

    lines.append("\n### By Priority (scored openings only)")
    priority_counts = Counter(o.priority for o in scored)
    for p in range(5, 0, -1):
        count = priority_counts.get(p, 0)
        if count > 0:
            label = {5: "Exceptional", 4: "Strong", 3: "Solid", 2: "Marginal", 1: "Weak"}[p]
            lines.append(f"- **Priority {p}** ({label}): {count}")

    # Campaign groups summary
    groups = {}
    for o in openings:
        if o.campaign_group:
            groups.setdefault(o.campaign_group, []).append(o)
    if groups:
        lines.append(f"\n### Campaign Groups ({len(groups)})")
        for label, members in sorted(groups.items()):
            lines.append(f"- **{label}**: {len(members)} openings")

    # Scored openings organized by category
    lines.append("\n---")
    lines.append("\n## Scored Openings by Category")

    for category in OPENING_CATEGORIES:
        cat_openings = [o for o in scored if o.category == category]
        if not cat_openings:
            continue

        lines.append(f"\n### {category} ({len(cat_openings)})")

        # Sort by weighted_score within category
        cat_openings.sort(key=lambda o: o.weighted_score, reverse=True)

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
                lines.append(f"\n**{i}. [P{o.priority} | {o.weighted_score:.2f}] {o.what_happened}**")
                lines.append(f"- **Who**: {o.who}")
                lines.append(f"- **When**: {o.when}")
                lines.append(f"- **Where**: {o.where}")
                lines.append(f"- **Gates**: target={o.gate_named_target} | ask={o.gate_binary_ask} | window={o.gate_time_window}")
                lines.append(f"- **Scores**: beyond-choir={o.score_beyond_choir} | pressure={o.score_pressure_point} | replication={o.score_replication} | winnability={o.score_winnability}")
                if o.score_rationale:
                    lines.append(f"- **Score rationale**: {o.score_rationale}")
                lines.append(f"- **Replication potential**: {o.replication_potential}")
                lines.append(f"- **Campaign status**: {o.campaign_status}")
                lines.append(f"- **Time sensitivity**: {o.time_sensitivity}")
                lines.append(f"- **Why this is an opening**: {o.raw_material_note}")
                if o.campaign_group:
                    lines.append(f"- **Campaign group**: {o.campaign_group}")
                lines.append(f"- **Source**: [{o.source_name}]({o.source_url})")
                if o.additional_sources:
                    for src in o.additional_sources:
                        lines.append(f"  - Also: [{src}]({src})")

    # Any uncategorized scored openings
    uncategorized = [o for o in scored if o.category not in OPENING_CATEGORIES]
    if uncategorized:
        lines.append(f"\n### Other/Uncategorized ({len(uncategorized)})")
        for i, o in enumerate(uncategorized, 1):
            lines.append(f"\n**{i}. [P{o.priority} | {o.weighted_score:.2f}] {o.what_happened}**")
            lines.append(f"- **Category**: {o.category}")
            lines.append(f"- **Issue Domain**: {o.issue_domain}")
            lines.append(f"- **Who**: {o.who}")
            lines.append(f"- **Where**: {o.where}")
            lines.append(f"- **Replication potential**: {o.replication_potential}")
            lines.append(f"- **Why this is an opening**: {o.raw_material_note}")
            lines.append(f"- **Source**: [{o.source_name}]({o.source_url})")

    # Watch List section
    if watch_list:
        lines.append("\n---")
        lines.append(f"\n## Watch List ({len(watch_list)})")
        lines.append("\n*These openings failed one or more gates (no named target, no specific ask, or time window closed) but may be worth monitoring.*")

        for i, o in enumerate(watch_list, 1):
            lines.append(f"\n**{i}. {o.what_happened}**")
            lines.append(f"- **Who**: {o.who}")
            lines.append(f"- **Where**: {o.where}")
            lines.append(f"- **Gates**: target={o.gate_named_target} | ask={o.gate_binary_ask} | window={o.gate_time_window}")
            if o.gate_fail_reason:
                lines.append(f"- **Why watch list**: {o.gate_fail_reason}")
            lines.append(f"- **Why this is an opening**: {o.raw_material_note}")
            lines.append(f"- **Source**: [{o.source_name}]({o.source_url})")

    lines.append("\n---")
    lines.append(f"\n*End of scan. {len(scored)} scored openings, {len(watch_list)} watch list.*")

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
        "Status", "Priority", "Weighted Score", "What Happened",
        "Campaign Group",
        "G: Target", "G: Ask", "G: Window", "Gate Fail Reason",
        "D: Beyond Choir", "D: Pressure Point", "D: Replication", "D: Winnability",
        "Score Rationale",
        "Replication Potential", "Campaign Status", "Time Sensitivity",
        "Why This Is an Opening",
        "Category", "Issue Domain",
        "Who", "When", "Where",
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
    watch_list_fill = PatternFill("solid", fgColor="E0E0E0")  # gray
    priority_labels = {5: "5 - Exceptional", 4: "4 - Strong", 3: "3 - Solid", 2: "2 - Marginal", 1: "1 - Weak"}

    wrap_alignment = Alignment(vertical="top", wrap_text=True)

    for row_idx, o in enumerate(openings, 2):
        additional = "; ".join(o.additional_sources) if o.additional_sources else ""
        status = "Watch List" if o.is_watch_list else "Scored"

        values = [
            status,
            priority_labels.get(o.priority, str(o.priority)) if not o.is_watch_list else "—",
            o.weighted_score if not o.is_watch_list else "",
            o.what_happened,
            o.campaign_group,
            o.gate_named_target,
            o.gate_binary_ask,
            o.gate_time_window,
            o.gate_fail_reason,
            o.score_beyond_choir if not o.is_watch_list else "",
            o.score_pressure_point if not o.is_watch_list else "",
            o.score_replication if not o.is_watch_list else "",
            o.score_winnability if not o.is_watch_list else "",
            o.score_rationale,
            o.replication_potential,
            o.campaign_status,
            o.time_sensitivity,
            o.raw_material_note,
            o.category,
            o.issue_domain,
            o.who,
            o.when,
            o.where,
            o.source_name,
            o.source_url,
            additional,
        ]

        for col, value in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=col, value=value)
            cell.alignment = wrap_alignment
            cell.border = thin_border

        # Color rows by status/priority
        if o.is_watch_list:
            for col in range(1, len(headers) + 1):
                ws.cell(row=row_idx, column=col).fill = watch_list_fill
        else:
            fill = priority_fills.get(o.priority)
            if fill:
                ws.cell(row=row_idx, column=1).fill = fill
                ws.cell(row=row_idx, column=2).fill = fill
                ws.cell(row=row_idx, column=3).fill = fill

    # Column widths
    col_widths = {
        1: 12,   # Status
        2: 16,   # Priority
        3: 14,   # Weighted Score
        4: 50,   # What Happened
        5: 30,   # Campaign Group
        6: 10,   # G: Target
        7: 10,   # G: Ask
        8: 10,   # G: Window
        9: 30,   # Gate Fail Reason
        10: 14,  # D: Beyond Choir
        11: 14,  # D: Pressure Point
        12: 14,  # D: Replication
        13: 14,  # D: Winnability
        14: 40,  # Score Rationale
        15: 40,  # Replication Potential
        16: 30,  # Campaign Status
        17: 25,  # Time Sensitivity
        18: 45,  # Why This Is an Opening
        19: 28,  # Category
        20: 28,  # Issue Domain
        21: 25,  # Who
        22: 16,  # When
        23: 20,  # Where
        24: 20,  # Source
        25: 35,  # Source URL
        26: 35,  # Additional Sources
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

    # By Status
    row += 1
    scored = [o for o in openings if not o.is_watch_list]
    watch_list = [o for o in openings if o.is_watch_list]
    summary.cell(row=row, column=1, value="By Status").font = summary_subheader_font
    row += 1
    summary.cell(row=row, column=1, value="Scored")
    summary.cell(row=row, column=2, value=len(scored))
    row += 1
    summary.cell(row=row, column=1, value="Watch List")
    summary.cell(row=row, column=2, value=len(watch_list))

    # By Priority (scored only)
    row += 2
    summary.cell(row=row, column=1, value="By Priority (scored)").font = summary_subheader_font
    row += 1
    priority_counts = Counter(o.priority for o in scored)
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
    scored = [o for o in openings if not o.is_watch_list]
    watch_list = [o for o in openings if o.is_watch_list]

    print(f"\n{'='*60}")
    print(f"  SCAN COMPLETE: {len(openings)} campaign openings identified")
    print(f"  Scored: {len(scored)} | Watch list: {len(watch_list)}")
    print(f"{'='*60}")

    # By category
    print("\n  By Category:")
    category_counts = Counter(o.category for o in openings)
    for cat in OPENING_CATEGORIES:
        count = category_counts.get(cat, 0)
        if count > 0:
            print(f"    {cat}: {count}")

    # By priority (scored only)
    print("\n  By Priority (scored openings):")
    priority_counts = Counter(o.priority for o in scored)
    for p in range(5, 0, -1):
        count = priority_counts.get(p, 0)
        if count > 0:
            label = {5: "Exceptional", 4: "Strong", 3: "Solid", 2: "Marginal", 1: "Weak"}[p]
            print(f"    Priority {p} ({label}): {count}")

    # Top 10 scored openings by weighted score
    top = sorted(scored, key=lambda o: (o.weighted_score, o.priority), reverse=True)[:10]
    print(f"\n  Top 10 Openings:")
    for i, o in enumerate(top, 1):
        print(f"    {i}. [P{o.priority} | {o.weighted_score:.2f}] {o.what_happened[:80]}")
        print(f"       Gates: target={o.gate_named_target} ask={o.gate_binary_ask} window={o.gate_time_window}")
        print(f"       Scores: choir={o.score_beyond_choir} pressure={o.score_pressure_point} repl={o.score_replication} win={o.score_winnability}")
        if o.campaign_group:
            print(f"       Group: {o.campaign_group}")
        if o.score_rationale:
            print(f"       Rationale: {o.score_rationale[:80]}")

    # Watch list summary
    if watch_list:
        print(f"\n  Watch List ({len(watch_list)} openings failed gates):")
        for i, o in enumerate(watch_list[:5], 1):
            print(f"    {i}. {o.what_happened[:70]}")
            print(f"       Gates: target={o.gate_named_target} ask={o.gate_binary_ask} window={o.gate_time_window}")
            if o.gate_fail_reason:
                print(f"       Reason: {o.gate_fail_reason[:70]}")
        if len(watch_list) > 5:
            print(f"    ... and {len(watch_list) - 5} more")

    print(f"\n{'='*60}")
