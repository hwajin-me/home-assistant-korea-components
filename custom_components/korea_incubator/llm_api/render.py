"""SVG renderer helpers for kr_public_data LLM tools.

The voice-satellite card renders ``featured_image`` and
``results[].image_url`` as ``<img>`` elements, which accept ``data:`` URLs.
We generate compact SVG tables/cards so the user sees a visual answer in
addition to the LLM narration.
"""
from __future__ import annotations

import base64
from typing import Iterable, Sequence

# Korean-capable system font stack (works on macOS, Windows, Android, iOS).
_FONT = (
    "system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',"
    "'Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif"
)

# Tailwind-ish dark palette so the cards harmonise with most HA themes.
_BG = "#0f172a"        # slate-900
_BG_ALT = "#1e293b"    # slate-800
_FG = "#e2e8f0"        # slate-200
_MUTED = "#94a3b8"     # slate-400
_DIVIDER = "#334155"   # slate-700
_DEFAULT_ACCENT = "#0ea5e9"  # sky-500


def _esc(text: str | None) -> str:
    if text is None:
        return ""
    s = str(text)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _trunc(text: str | None, limit: int) -> str:
    if text is None:
        return ""
    s = str(text)
    return s if len(s) <= limit else s[: max(limit - 1, 1)] + "…"


def _to_data_url(svg: str) -> str:
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def svg_table(
    title: str,
    columns: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    subtitle: str | None = None,
    accent: str = _DEFAULT_ACCENT,
    column_truncations: Sequence[int] | None = None,
    width: int = 520,
    empty_message: str = "No data",
) -> str:
    """Return a data: URL pointing at an SVG table card."""
    if not columns:
        columns = ["Value"]

    n_cols = len(columns)
    col_w = [width // n_cols] * n_cols
    # last column absorbs the rounding remainder
    col_w[-1] += width - sum(col_w)

    if column_truncations is None:
        column_truncations = [max(8, (col_w[i] // 9) - 1) for i in range(n_cols)]

    row_h = 30
    pad_x = 18
    title_y = 30
    subtitle_y = 50
    header_h = 64 if subtitle else 48
    column_band_h = 26
    body_top = header_h + column_band_h
    body_h = max(row_h * max(len(rows), 1), row_h)
    height = body_top + body_h + 14

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
    )
    # Card background (rounded)
    parts.append(
        f'<rect width="{width}" height="{height}" rx="14" ry="14" fill="{_BG}"/>'
    )
    # Accent header band
    parts.append(
        f'<path d="M0 14 Q0 0 14 0 H{width - 14} Q{width} 0 {width} 14 V{header_h} '
        f'H0 Z" fill="{accent}"/>'
    )
    parts.append(
        f'<text x="{pad_x}" y="{title_y}" font-family="{_FONT}" font-size="18" '
        f'font-weight="700" fill="white">{_esc(_trunc(title, 60))}</text>'
    )
    if subtitle:
        parts.append(
            f'<text x="{pad_x}" y="{subtitle_y}" font-family="{_FONT}" '
            f'font-size="12" fill="rgba(255,255,255,0.85)">'
            f"{_esc(_trunc(subtitle, 80))}</text>"
        )

    # Column headers
    col_y = header_h + 18
    x_cursor = pad_x
    for i, col in enumerate(columns):
        parts.append(
            f'<text x="{x_cursor}" y="{col_y}" font-family="{_FONT}" '
            f'font-size="11" font-weight="600" fill="{_MUTED}" '
            f'letter-spacing="0.6">{_esc(col).upper()}</text>'
        )
        x_cursor += col_w[i]

    # Body rows
    if not rows:
        parts.append(
            f'<text x="{width / 2}" y="{body_top + row_h - 8}" '
            f'font-family="{_FONT}" font-size="13" fill="{_MUTED}" '
            f'text-anchor="middle">{_esc(empty_message)}</text>'
        )
    else:
        for ri, row in enumerate(rows):
            ry = body_top + ri * row_h
            if ri % 2 == 0:
                parts.append(
                    f'<rect x="0" y="{ry}" width="{width}" height="{row_h}" '
                    f'fill="{_BG_ALT}"/>'
                )
            x = pad_x
            for ci in range(n_cols):
                cell = row[ci] if ci < len(row) else ""
                limit = column_truncations[ci]
                parts.append(
                    f'<text x="{x}" y="{ry + 20}" font-family="{_FONT}" '
                    f'font-size="13" fill="{_FG}">'
                    f"{_esc(_trunc(cell, limit))}</text>"
                )
                x += col_w[ci]

    parts.append("</svg>")
    return _to_data_url("".join(parts))


def svg_card(
    title: str,
    lines: Sequence[tuple[str, str]],
    *,
    subtitle: str | None = None,
    accent: str = _DEFAULT_ACCENT,
    big_value: str | None = None,
    big_value_caption: str | None = None,
    width: int = 360,
) -> str:
    """A single-card layout: header + optional big value + key/value lines."""
    line_h = 26
    pad_x = 22
    header_h = 60 if subtitle else 44
    big_block_h = 70 if big_value else 0
    body_top = header_h + big_block_h + (8 if big_value else 12)
    body_h = max(line_h * max(len(lines), 1), line_h)
    height = body_top + body_h + 16

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
    )
    parts.append(
        f'<rect width="{width}" height="{height}" rx="16" ry="16" fill="{_BG}"/>'
    )
    parts.append(
        f'<path d="M0 16 Q0 0 16 0 H{width - 16} Q{width} 0 {width} 16 V{header_h} '
        f'H0 Z" fill="{accent}"/>'
    )
    parts.append(
        f'<text x="{pad_x}" y="28" font-family="{_FONT}" font-size="17" '
        f'font-weight="700" fill="white">{_esc(_trunc(title, 50))}</text>'
    )
    if subtitle:
        parts.append(
            f'<text x="{pad_x}" y="48" font-family="{_FONT}" font-size="12" '
            f'fill="rgba(255,255,255,0.85)">{_esc(_trunc(subtitle, 60))}</text>'
        )

    if big_value is not None:
        parts.append(
            f'<text x="{pad_x}" y="{header_h + 44}" font-family="{_FONT}" '
            f'font-size="32" font-weight="700" fill="{_FG}">'
            f"{_esc(_trunc(big_value, 22))}</text>"
        )
        if big_value_caption:
            parts.append(
                f'<text x="{pad_x}" y="{header_h + 64}" font-family="{_FONT}" '
                f'font-size="12" fill="{_MUTED}">'
                f"{_esc(_trunc(big_value_caption, 50))}</text>"
            )

    for i, (label, value) in enumerate(lines or []):
        y = body_top + i * line_h + 18
        parts.append(
            f'<text x="{pad_x}" y="{y}" font-family="{_FONT}" font-size="12" '
            f'fill="{_MUTED}">{_esc(_trunc(label, 18))}</text>'
        )
        parts.append(
            f'<text x="{width - pad_x}" y="{y}" font-family="{_FONT}" '
            f'font-size="13" font-weight="600" fill="{_FG}" '
            f'text-anchor="end">{_esc(_trunc(value, 22))}</text>'
        )

    parts.append("</svg>")
    return _to_data_url("".join(parts))


def grid_results(
    items: Iterable[tuple[str, list[tuple[str, str]], dict | None]],
    *,
    accent: str = _DEFAULT_ACCENT,
) -> list[dict[str, str]]:
    """Build a ``results`` array of SVG-card image entries.

    Each item is ``(title, [(label, value), ...], extra_dict_or_None)``.
    The returned list is suitable for ``toolResult["results"]`` so the
    voice-satellite card renders a 2-column grid.
    """
    out: list[dict[str, str]] = []
    for title, lines, extra in items:
        url = svg_card(title, lines, accent=accent, width=320)
        entry = {"image_url": url, "thumbnail_url": url, "title": title}
        if extra:
            entry.update({k: v for k, v in extra.items() if v is not None})
        out.append(entry)
    return out
