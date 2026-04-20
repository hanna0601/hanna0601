#!/usr/bin/env python3
"""Generate language-stats.svg from GitHub repository language byte counts."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


USERNAME = os.getenv("GITHUB_USERNAME", "hanna0601")
OUTPUT = Path(os.getenv("LANGUAGE_STATS_OUTPUT", "language-stats.svg"))
INCLUDE_FORKS = os.getenv("LANGUAGE_STATS_INCLUDE_FORKS", "false").lower() == "true"
INCLUDE_ARCHIVED = os.getenv("LANGUAGE_STATS_INCLUDE_ARCHIVED", "false").lower() == "true"
TOKEN = os.getenv("LANG_STATS_TOKEN")

WIDTH = 920
BAR_WIDTH = 888
BAR_X = 16
BAR_Y = 54
COLORS = {
    "C": "#555555",
    "C#": "#178600",
    "C++": "#f34b7d",
    "CSS": "#663399",
    "GLSL": "#5686a5",
    "HLSL": "#aace60",
    "HTML": "#e34c26",
    "Java": "#b07219",
    "JavaScript": "#f1e05a",
    "Jupyter Notebook": "#da5b0b",
    "PHP": "#4F5D95",
    "Python": "#3572a5",
    "Ruby": "#701516",
    "Scala": "#c22d40",
    "Shell": "#89e051",
    "Swift": "#f05138",
    "TeX": "#3d6117",
    "TypeScript": "#3178c6",
    "Other": "#8c959f",
}


def github_json(url: str) -> tuple[object, dict[str, str]]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USERNAME}-profile-language-stats",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            headers_out = {k.lower(): v for k, v in response.headers.items()}
            return json.loads(response.read().decode("utf-8")), headers_out
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API request failed: {exc.code} {url}\n{body}") from exc


def paginated(url: str) -> list[dict]:
    items: list[dict] = []
    next_url: str | None = url
    while next_url:
        data, headers = github_json(next_url)
        if not isinstance(data, list):
            raise RuntimeError(f"Expected list response from {next_url}")
        items.extend(data)
        next_url = parse_next_link(headers.get("link", ""))
    return items


def parse_next_link(link_header: str) -> str | None:
    for part in link_header.split(","):
        section = part.strip()
        if 'rel="next"' not in section:
            continue
        start = section.find("<")
        end = section.find(">")
        if start != -1 and end != -1:
            return section[start + 1 : end]
    return None


def fetch_repositories() -> tuple[list[dict], str]:
    if TOKEN:
        url = (
            "https://api.github.com/user/repos"
            "?visibility=all&affiliation=owner,collaborator,organization_member"
            "&per_page=100&sort=full_name"
        )
        source_label = "accessible"
    else:
        url = f"https://api.github.com/users/{USERNAME}/repos?type=owner&per_page=100&sort=full_name"
        source_label = "public"

    repos = [
        repo
        for repo in paginated(url)
        if repo.get("owner", {}).get("login", "").lower() == USERNAME.lower()
        and (INCLUDE_FORKS or not repo.get("fork"))
        and (INCLUDE_ARCHIVED or not repo.get("archived"))
    ]
    return repos, source_label


def aggregate_languages(repos: list[dict]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for repo in repos:
        full_name = repo["full_name"]
        data, _ = github_json(f"https://api.github.com/repos/{full_name}/languages")
        if not isinstance(data, dict):
            continue
        for language, byte_count in data.items():
            totals[language] = totals.get(language, 0) + int(byte_count)
    return totals


def language_rows(totals: dict[str, int], limit: int = 8) -> list[tuple[str, int]]:
    ordered = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    shown = ordered[:limit]
    other = sum(value for _, value in ordered[limit:])
    if other:
        shown.append(("Other", other))
    return shown


def bar_segments(rows: list[tuple[str, int]]) -> list[tuple[str, int, int]]:
    total = sum(value for _, value in rows)
    if total <= 0:
        return []

    raw_widths = [value * BAR_WIDTH / total for _, value in rows]
    widths = [max(1, round(width)) for width in raw_widths]
    diff = BAR_WIDTH - sum(widths)
    widths[0] += diff

    x = 0
    segments = []
    for (language, _), width in zip(rows, widths):
        segments.append((language, x, width))
        x += width
    return segments


def esc(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_svg(rows: list[tuple[str, int]], repo_count: int, source_label: str) -> str:
    total = sum(value for _, value in rows)
    if total <= 0:
        rows = [("No language data", 1)]
        total = 1

    legend_positions = [
        (92, 98),
        (360, 98),
        (625, 98),
        (92, 129),
        (360, 129),
        (625, 129),
        (92, 160),
        (360, 160),
        (625, 160),
    ]
    height = 170

    rects = []
    for language, x, width in bar_segments(rows):
        rects.append(
            f'      <rect x="{x}" y="0" width="{width}" height="14" fill="{COLORS.get(language, COLORS["Other"])}"/>'
        )

    legend = []
    for (language, value), (x, y) in zip(rows, legend_positions):
        percentage = value * 100 / total
        label = f"{language} {percentage:.1f}%"
        color = COLORS.get(language, COLORS["Other"])
        legend.append(
            "\n".join(
                [
                    f'  <circle cx="{x}" cy="{y - 7}" r="7" fill="{color}"/>',
                    f'  <text x="{x + 22}" y="{y}" class="label">{esc(label)}</text>',
                ]
            )
        )

    scope = f"{source_label} non-fork repositories"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" role="img" aria-labelledby="title desc">
  <title id="title">Most used languages</title>
  <desc id="desc">Language usage across Hanna Zhang's {scope}, calculated from GitHub language byte counts.</desc>
  <style>
    .title {{ font: 24px -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; fill: #0969da; }}
    .label {{ font: 18px -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; fill: #6e6e6e; }}
  </style>

  <rect width="{WIDTH}" height="{height}" fill="#ffffff"/>
  <text x="460" y="28" text-anchor="middle" class="title">Most used languages</text>

  <g transform="translate({BAR_X} {BAR_Y})">
    <clipPath id="rounded-bar">
      <rect x="0" y="0" width="{BAR_WIDTH}" height="14" rx="7" ry="7"/>
    </clipPath>
    <g clip-path="url(#rounded-bar)">
{chr(10).join(rects)}
    </g>
  </g>

{chr(10).join(legend)}
</svg>
'''


def main() -> int:
    repos, source_label = fetch_repositories()
    totals = aggregate_languages(repos)
    rows = language_rows(totals)
    OUTPUT.write_text(render_svg(rows, len(repos), source_label), encoding="utf-8")

    print(f"Updated {OUTPUT} from {len(repos)} {source_label} non-fork repositories.")
    for language, value in rows:
        print(f"{language}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
