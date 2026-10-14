"""Self-contained HTML report generator for Launchpad bugs."""

from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def format_timestamp(iso_str: str | None) -> str:
    """Format an ISO timestamp into a concise UTC string."""
    if not iso_str:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(iso_str)[:16]


def get_status_class(status: str) -> str:
    """Return CSS class for a given task status."""
    st = status.lower().replace("'", "").replace(" ", "-")
    if st in ("in-progress", "triaged"):
        return "badge-inprogress"
    if st in ("fix-committed",):
        return "badge-fixcommitted"
    if st in ("fix-released",):
        return "badge-fixreleased"
    if st in ("confirmed",):
        return "badge-confirmed"
    if st in ("incomplete", "incomplete-with-response", "incomplete-without-response"):
        return "badge-incomplete"
    if st in ("new",):
        return "badge-new"
    if st in ("wont-fix", "invalid", "expired", "opinion"):
        return "badge-closed"
    return "badge-default"


def generate_html_report(
    bugs: dict[str, dict[str, Any]],
    output_path: Path | str,
    scan_time_utc: datetime | None = None,
    packages_scanned: list[str] | None = None,
    title: str | None = None,
) -> None:
    """Generate a self-contained, responsive HTML report file with interactive expand/filter/sort."""
    scan_dt = scan_time_utc or datetime.now(UTC)
    scan_str = scan_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

    # Sort bugs by last_activity_time descending
    sorted_bugs = sorted(
        bugs.values(),
        key=lambda b: b.get("last_activity_time") or b.get("date_last_updated") or "",
        reverse=True,
    )

    # Unique packages represented
    pkgs_found = sorted({b.get("package", "unknown") for b in sorted_bugs})
    all_pkgs = sorted(set(packages_scanned or []).union(pkgs_found))
    pkgs_label = ", ".join(all_pkgs) if all_pkgs else "monitored source packages"

    pkg_count = len(all_pkgs)
    pkg_word = "package" if pkg_count == 1 else "packages"
    dashboard_title = title or f"Ubuntu Bug Status ({pkg_count} {pkg_word})"

    # Precompute summary counts
    total_bugs = len(sorted_bugs)
    status_counts: dict[str, int] = {}
    for b in sorted_bugs:
        for t in b.get("tasks", []):
            if not t.get("is_complete"):
                st = t.get("status", "Unknown")
                status_counts[st] = status_counts.get(st, 0) + 1

    # Build bug rows HTML
    rows_html: list[str] = []
    for b in sorted_bugs:
        b_id = b["id"]
        title = html.escape(b.get("title", ""))
        web_link = html.escape(b.get("web_link", f"https://bugs.launchpad.net/bugs/{b_id}"))
        pkg = html.escape(b.get("package", "unknown"))
        owner = html.escape(b.get("owner", "Unknown"))
        tags = [html.escape(tag) for tag in b.get("tags", [])]
        last_act_time = format_timestamp(b.get("last_activity_time"))
        iso_last_act = html.escape(b.get("last_activity_time") or "")
        last_act_summary = html.escape(b.get("last_activity_summary") or "Bug updated")

        tasks = b.get("tasks", [])
        open_tasks = [t for t in tasks if not t.get("is_complete")]
        closed_tasks = [t for t in tasks if t.get("is_complete")]

        # Series / targets of open tasks
        open_targets = [html.escape(t.get("target_display", t.get("target", ""))) for t in open_tasks]
        open_targets_str = ", ".join(open_targets) if open_targets else "None"

        # Unique statuses present on open tasks
        open_statuses = sorted({t.get("status", "Unknown") for t in open_tasks})
        status_badges = "".join(
            f'<span class="status-badge {get_status_class(st)}">{html.escape(st)}</span>' for st in open_statuses
        )

        task_summary_pill = (
            f'<span class="task-count-pill">'
            f'<strong class="text-orange">{len(open_tasks)} Open</strong> / '
            f'<span class="text-gray">{len(closed_tasks)} Closed</span>'
            f"</span>"
        )

        # Build tasks table inside details row
        task_rows: list[str] = []
        for t in tasks:
            t_target = html.escape(t.get("target_display", t.get("target", "")))
            t_status = html.escape(t.get("status", "Unknown"))
            t_assignee = html.escape(t.get("assignee") or "Unassigned")
            t_link = html.escape(t.get("web_link", ""))
            t_class = get_status_class(t.get("status", ""))
            t_link_tag = (
                f'<a href="{t_link}" target="_blank" rel="noopener" class="link-ext">Launchpad ↗</a>' if t_link else ""
            )

            task_rows.append(
                f"<tr>"
                f'<td class="font-mono">{t_target}</td>'
                f'<td><span class="status-badge {t_class}">{t_status}</span></td>'
                f"<td>{t_assignee}</td>"
                f"<td>{t_link_tag}</td>"
                f"</tr>"
            )
        tasks_tbody = "".join(task_rows)

        if tags:
            tag_pills = "".join(f'<span class="tag-pill">{t}</span>' for t in tags)
        else:
            tag_pills = '<span class="text-gray">None</span>'

        statuses_json = html.escape(json.dumps([s.lower() for s in open_statuses]))

        row = f"""
        <tr class="bug-row" id="row-{b_id}" onclick="toggleDetails({b_id})"
            data-bugid="{b_id}" data-package="{pkg.lower()}"
            data-statuses="{statuses_json}" data-lastact="{iso_last_act}">
            <td class="col-toggle"><span class="toggle-icon" id="toggle-{b_id}">▶</span></td>
            <td class="col-id font-mono">
                <a href="{web_link}" target="_blank" rel="noopener" onclick="event.stopPropagation()">#{b_id}</a>
            </td>
            <td class="col-title" title="{title}">{title}</td>
            <td class="col-package font-mono"><span class="package-pill">{pkg}</span></td>
            <td class="col-tasks">
                <div class="tasks-summary-wrap">
                    {task_summary_pill}
                    <div class="status-badges-group">{status_badges}</div>
                </div>
            </td>
            <td class="col-activity" title="{last_act_summary}">
                <div class="activity-wrap">
                    <span class="activity-time font-mono">{last_act_time}</span>
                    <span class="activity-desc text-muted">{last_act_summary}</span>
                </div>
            </td>
        </tr>
        <tr class="details-row" id="details-{b_id}" style="display: none;">
            <td colspan="6">
                <div class="details-panel">
                    <div class="details-grid">
                        <div class="details-tasks-card">
                            <h4>Target Tasks ({len(tasks)} total)</h4>
                            <table class="subtable">
                                <thead>
                                    <tr>
                                        <th>Target</th>
                                        <th>Status</th>
                                        <th>Assignee</th>
                                        <th>Action</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {tasks_tbody}
                                </tbody>
                            </table>
                        </div>
                        <div class="details-meta-card">
                            <h4>Bug Details</h4>
                            <div class="meta-item"><strong>Reporter:</strong> <span>{owner}</span></div>
                            <div class="meta-item">
                                <strong>Created:</strong>
                                <span class="font-mono">{format_timestamp(b.get("date_created"))}</span>
                            </div>
                            <div class="meta-item">
                                <strong>Last Updated:</strong>
                                <span class="font-mono">{format_timestamp(b.get("date_last_updated"))}</span>
                            </div>
                            <div class="meta-item"><strong>Last Activity:</strong> <span>{last_act_summary}</span></div>
                            <div class="meta-item"><strong>Active Targets:</strong>
                                <span class="text-sm">{open_targets_str}</span>
                            </div>
                            <div class="meta-item"><strong>Tags:</strong>
                                <div class="tags-wrap">{tag_pills}</div>
                            </div>
                        </div>
                    </div>
                </div>
            </td>
        </tr>
        """
        rows_html.append(row)

    table_body = "\n".join(rows_html)

    # Package options for filter
    pkg_options = "".join(f'<option value="{html.escape(p.lower())}">{html.escape(p)}</option>' for p in pkgs_found)

    # Status options for filter
    unique_statuses = sorted(status_counts.keys())
    status_options = "".join(
        f'<option value="{html.escape(s.lower())}">{html.escape(s)} ({status_counts[s]})</option>'
        for s in unique_statuses
    )

    # Summary cards HTML
    status_summary_pills = "".join(
        f'<span class="summary-chip"><span class="chip-status {get_status_class(s)}"></span> '
        f"{html.escape(s)}: <strong>{count}</strong></span>"
        for s, count in status_counts.items()
    )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(dashboard_title)}</title>
<style>
  :root {{
    --bg-main: #f7f7f7;
    --bg-card: #ffffff;
    --text-main: #111827;
    --text-muted: #6b7280;
    --border-color: #e5e7eb;
    --brand-canonical: #77216F;
    --brand-orange: #E95420;
    --brand-hover: #380C2A;
    --link-color: #1d4ed8;
    --link-hover: #1e40af;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg-main);
    color: var(--text-main);
    line-height: 1.5;
    padding: 24px 32px;
  }}

  a {{ color: var(--link-color); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .font-mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 0.9em; }}
  .text-muted {{ color: var(--text-muted); }}
  .text-orange {{ color: var(--brand-orange); }}
  .text-gray {{ color: #9ca3af; }}
  .text-sm {{ font-size: 0.85em; }}

  /* Header */
  .header {{
    background: linear-gradient(135deg, var(--brand-canonical), var(--brand-hover));
    color: white;
    padding: 24px 32px;
    border-radius: 12px;
    margin-bottom: 24px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
  }}
  .header h1 {{ font-size: 1.75rem; font-weight: 700; margin-bottom: 8px; }}
  .header p {{ color: rgba(255, 255, 255, 0.85); font-size: 0.95rem; }}

  /* Metric cards */
  .stats-bar {{
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    margin-bottom: 24px;
  }}
  .stat-card {{
    background: var(--bg-card);
    padding: 16px 20px;
    border-radius: 8px;
    border: 1px solid var(--border-color);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    flex: 1;
    min-width: 180px;
  }}
  .stat-card .label {{
    font-size: 0.8rem;
    text-transform: uppercase;
    color: var(--text-muted);
    font-weight: 600;
    letter-spacing: 0.05em;
  }}
  .stat-card .value {{ font-size: 1.8rem; font-weight: 700; color: var(--brand-canonical); margin-top: 4px; }}
  .summary-chips {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 4px; }}
  .summary-chip {{
    font-size: 0.85rem;
    background: #f3f4f6;
    padding: 3px 8px;
    border-radius: 4px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }}
  .chip-status {{ width: 8px; height: 8px; border-radius: 50%; }}

  /* Controls bar */
  .controls-bar {{
    background: var(--bg-card);
    padding: 16px 20px;
    border-radius: 8px;
    border: 1px solid var(--border-color);
    margin-bottom: 20px;
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    align-items: center;
    justify-content: space-between;
  }}
  .filter-group {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: center; flex: 1; }}
  .search-input {{
    padding: 8px 12px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 0.9rem;
    min-width: 260px;
    flex: 1;
  }}
  .select-filter {{
    padding: 8px 12px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 0.9rem;
    background: white;
  }}
  .btn {{
    padding: 8px 14px;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 600;
    cursor: pointer;
    border: 1px solid transparent;
    transition: background 0.15s ease;
  }}
  .btn-outline {{ background: white; border-color: #d1d5db; color: #374151; }}
  .btn-outline:hover {{ background: #f9fafb; }}

  /* Table */
  .table-container {{
    background: var(--bg-card);
    border-radius: 8px;
    border: 1px solid var(--border-color);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    overflow-x: auto;
  }}
  table.bugs-table {{
    width: 100%;
    border-collapse: collapse;
    text-align: left;
    font-size: 0.9rem;
  }}
  table.bugs-table th {{
    background: #f9fafb;
    padding: 12px 16px;
    font-weight: 600;
    color: #4b5563;
    border-bottom: 1px solid var(--border-color);
    user-select: none;
    cursor: pointer;
  }}
  table.bugs-table th:hover {{ background: #f3f4f6; color: #111827; }}
  table.bugs-table td {{
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-color);
    vertical-align: middle;
  }}

  /* Main row */
  .bug-row {{ cursor: pointer; transition: background 0.1s ease; }}
  .bug-row:hover {{ background: #fdf2e9; }}
  .bug-row.expanded {{ background: #fbf0e8; font-weight: 500; }}
  .col-toggle {{ width: 36px; text-align: center; color: var(--text-muted); font-size: 0.8rem; }}
  .toggle-icon {{ display: inline-block; transition: transform 0.2s ease; }}
  .expanded .toggle-icon {{ transform: rotate(90deg); color: var(--brand-orange); }}
  .col-id {{ width: 100px; font-weight: 600; white-space: nowrap; }}
  .col-title {{ max-width: 440px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .col-package {{ width: 160px; white-space: nowrap; }}
  .col-tasks {{ width: 260px; }}
  .col-activity {{ width: 220px; }}

  .tasks-summary-wrap {{ display: flex; flex-direction: column; gap: 4px; }}
  .task-count-pill {{ font-size: 0.8rem; }}
  .status-badges-group {{ display: flex; flex-wrap: wrap; gap: 4px; }}

  .activity-wrap {{ display: flex; flex-direction: column; gap: 2px; }}
  .activity-time {{ font-size: 0.85rem; font-weight: 600; color: #374151; }}
  .activity-desc {{
    font-size: 0.75rem;
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}

  /* Badges */
  .package-pill {{
    background: #e0e7ff;
    color: #3730a3;
    padding: 2px 8px;
    border-radius: 9999px;
    font-size: 0.8rem;
    font-weight: 600;
  }}
  .status-badge {{
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: capitalize;
  }}
  .badge-inprogress {{ background: #ffedd5; color: #9a3412; }}
  .badge-fixcommitted {{ background: #ccfbf1; color: #115e59; }}
  .badge-fixreleased {{ background: #dcfce7; color: #166534; }}
  .badge-confirmed {{ background: #f3e8ff; color: #6b21a8; }}
  .badge-incomplete {{ background: #fef9c3; color: #854d0e; }}
  .badge-new {{ background: #dbeafe; color: #1e40af; }}
  .badge-closed {{ background: #e5e7eb; color: #374151; }}
  .badge-default {{ background: #f3f4f6; color: #374151; }}

  /* Details row */
  .details-row td {{ padding: 0 !important; background: #fafafa; border-bottom: 2px solid #e5e7eb; }}
  .details-panel {{ padding: 20px 24px; }}
  .details-grid {{ display: grid; grid-template-columns: 3fr 2fr; gap: 24px; }}
  .details-tasks-card, .details-meta-card {{
    background: white;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 16px;
    box-shadow: 0 1px 2px rgba(0,0,0,0.03);
  }}
  .details-tasks-card h4, .details-meta-card h4 {{
    font-size: 0.95rem;
    font-weight: 700;
    color: #374151;
    margin-bottom: 12px;
  }}

  table.subtable {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  table.subtable th {{
    background: #f9fafb;
    padding: 8px 10px;
    font-weight: 600;
    color: var(--text-muted);
    border-bottom: 1px solid var(--border-color);
    text-align: left;
  }}
  table.subtable td {{ padding: 8px 10px; border-bottom: 1px solid #f3f4f6; }}
  .link-ext {{ font-weight: 600; font-size: 0.8rem; }}

  .meta-item {{ display: flex; gap: 8px; margin-bottom: 8px; font-size: 0.85rem; }}
  .meta-item strong {{ min-width: 105px; color: var(--text-muted); }}
  .tags-wrap {{ display: flex; flex-wrap: wrap; gap: 4px; }}
  .tag-pill {{ background: #f3f4f6; color: #4b5563; padding: 1px 6px; border-radius: 4px; font-size: 0.75rem; }}

  .no-bugs {{ text-align: center; padding: 48px 16px; color: var(--text-muted); font-size: 1.1rem; }}

  @media (max-width: 1024px) {{
    body {{ padding: 16px; }}
    .details-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>

<div class="header">
  <h1>{html.escape(dashboard_title)}</h1>
  <p>Active open bugs filed against: {html.escape(pkgs_label)}. Generated on {scan_str}.</p>
</div>

<div class="stats-bar">
  <div class="stat-card">
    <div class="label">Total Open Bugs</div>
    <div class="value" id="stat-total">{total_bugs}</div>
  </div>
  <div class="stat-card">
    <div class="label">Source Packages Tracked</div>
    <div class="value">{len(all_pkgs)}</div>
  </div>
  <div class="stat-card" style="flex: 2;">
    <div class="label">Active Task Status Breakdown</div>
    <div class="summary-chips">
      {status_summary_pills or '<span class="text-muted">No open tasks</span>'}
    </div>
  </div>
</div>

<div class="controls-bar">
  <div class="filter-group">
    <input type="text" id="search-box" class="search-input"
           placeholder="Search by bug #, summary, series, package, tag..." oninput="applyFilters()">
    <select id="filter-package" class="select-filter" onchange="applyFilters()">
      <option value="">All Packages ({len(pkgs_found)})</option>
      {pkg_options}
    </select>
    <select id="filter-status" class="select-filter" onchange="applyFilters()">
      <option value="">All Open Statuses</option>
      {status_options}
    </select>
  </div>
  <div class="action-group">
    <button type="button" class="btn btn-outline" id="btn-toggle-all" onclick="toggleAllDetails()">
      Expand All
    </button>
  </div>
</div>

<div class="table-container">
  <table class="bugs-table" id="bugs-table">
    <thead>
      <tr>
        <th class="col-toggle"></th>
        <th onclick="sortTable('id')">Bug ID ↕</th>
        <th onclick="sortTable('title')">Summary / Title ↕</th>
        <th onclick="sortTable('package')">Source Package ↕</th>
        <th>Active Tasks Summary</th>
        <th onclick="sortTable('lastact')">Last Activity (UTC) ↕</th>
      </tr>
    </thead>
    <tbody id="bugs-tbody">
      {table_body if sorted_bugs else '<tr><td colspan="6" class="no-bugs">No open bugs found!</td></tr>'}
    </tbody>
  </table>
</div>

<script>
  let allExpanded = false;
  let sortDirection = {{ 'lastact': -1, 'id': 1, 'title': 1, 'package': 1 }};

  function toggleDetails(bugId) {{
    const detailsRow = document.getElementById('details-' + bugId);
    const mainRow = document.getElementById('row-' + bugId);
    if (!detailsRow || !mainRow) return;

    if (detailsRow.style.display === 'none') {{
      detailsRow.style.display = 'table-row';
      mainRow.classList.add('expanded');
    }} else {{
      detailsRow.style.display = 'none';
      mainRow.classList.remove('expanded');
    }}
  }}

  function toggleAllDetails() {{
    const detailsRows = document.querySelectorAll('.details-row');
    const mainRows = document.querySelectorAll('.bug-row');
    const btn = document.getElementById('btn-toggle-all');
    allExpanded = !allExpanded;

    detailsRows.forEach(r => {{
      // Only expand visible rows
      const bId = r.id.replace('details-', '');
      const mainRow = document.getElementById('row-' + bId);
      if (mainRow && mainRow.style.display !== 'none') {{
        r.style.display = allExpanded ? 'table-row' : 'none';
      }} else {{
        r.style.display = 'none';
      }}
    }});

    mainRows.forEach(r => {{
      if (r.style.display !== 'none') {{
        if (allExpanded) r.classList.add('expanded');
        else r.classList.remove('expanded');
      }}
    }});

    btn.textContent = allExpanded ? 'Collapse All' : 'Expand All';
  }}

  function applyFilters() {{
    const search = document.getElementById('search-box').value.toLowerCase().trim();
    const pkgFilter = document.getElementById('filter-package').value;
    const statusFilter = document.getElementById('filter-status').value;

    const rows = document.querySelectorAll('.bug-row');
    let visibleCount = 0;

    rows.forEach(r => {{
      const bId = r.getAttribute('data-bugid');
      const detailsRow = document.getElementById('details-' + bId);
      const pkg = r.getAttribute('data-package') || '';
      const statuses = JSON.parse(r.getAttribute('data-statuses') || '[]');
      const textContent = (r.textContent + ' ' + (detailsRow ? detailsRow.textContent : '')).toLowerCase();

      let matchSearch = !search || textContent.includes(search);
      let matchPkg = !pkgFilter || pkg === pkgFilter;
      let matchStatus = !statusFilter || statuses.includes(statusFilter);

      if (matchSearch && matchPkg && matchStatus) {{
        r.style.display = '';
        visibleCount++;
      }} else {{
        r.style.display = 'none';
        if (detailsRow) detailsRow.style.display = 'none';
        r.classList.remove('expanded');
      }}
    }});

    document.getElementById('stat-total').textContent = visibleCount;
  }}

  function sortTable(column) {{
    const tbody = document.getElementById('bugs-tbody');
    const rows = Array.from(tbody.querySelectorAll('.bug-row'));
    if (!rows.length) return;

    sortDirection[column] = -1 * (sortDirection[column] || 1);
    const dir = sortDirection[column];

    rows.sort((a, b) => {{
      let valA, valB;
      if (column === 'id') {{
        valA = parseInt(a.getAttribute('data-bugid'), 10);
        valB = parseInt(b.getAttribute('data-bugid'), 10);
      }} else if (column === 'lastact') {{
        valA = a.getAttribute('data-lastact') || '';
        valB = b.getAttribute('data-lastact') || '';
      }} else if (column === 'package') {{
        valA = a.getAttribute('data-package') || '';
        valB = b.getAttribute('data-package') || '';
      }} else {{
        valA = a.querySelector('.col-' + column)?.textContent.trim() || '';
        valB = b.querySelector('.col-' + column)?.textContent.trim() || '';
      }}

      if (valA < valB) return -1 * dir;
      if (valA > valB) return 1 * dir;
      return 0;
    }});

    // Re-append sorted rows with their details rows
    rows.forEach(r => {{
      const bId = r.getAttribute('data-bugid');
      const detailsRow = document.getElementById('details-' + bId);
      tbody.appendChild(r);
      if (detailsRow) tbody.appendChild(detailsRow);
    }});
  }}
</script>

</body>
</html>
"""

    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(html_content, encoding="utf-8")
