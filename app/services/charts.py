import plotly.graph_objects as go
import plotly.io as pio


def build_streams_chart(streams: list[dict]) -> str | None:
    """Build an interactive Plotly time-series chart from stream records.

    Args:
        streams: list of dicts with keys: timestamp_offset, watts, heartrate, cadence, etc.

    Returns:
        HTML string to embed, or None if no data.
    """
    if not streams:
        return None

    times = [s["timestamp_offset"] for s in streams]
    # Convert seconds to mm:ss labels
    time_labels = [f"{t // 60}:{t % 60:02d}" for t in times]

    fig = go.Figure()

    series = [
        ("watts", "Power (W)", "#3273dc"),
        ("heartrate", "Heart Rate (bpm)", "#ff3860"),
        ("cadence", "Cadence (rpm)", "#23d160"),
    ]

    has_data = False
    for key, label, color in series:
        values = [s.get(key) for s in streams]
        if any(v is not None for v in values):
            has_data = True
            fig.add_trace(go.Scatter(
                x=times,
                y=values,
                mode="lines",
                name=label,
                line=dict(color=color, width=1.5),
                hovertemplate=f"{label}: %{{y:.0f}}<extra></extra>",
            ))

    if not has_data:
        return None

    fig.update_layout(
        xaxis_title="Time (seconds)",
        yaxis_title="Value",
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=450,
        margin=dict(l=50, r=20, t=30, b=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    return pio.to_html(fig, full_html=False, include_plotlyjs="cdn")


ZONE_COLORS = ["#3298dc", "#48c78e", "#ffe08a", "#ffa94d", "#f14668"]


def _time_in_zones(streams: list[dict], key: str, bounds: list[int]) -> list[int]:
    """Sum sample durations into 5 zones defined by lower bounds.

    Sample duration is derived from the gap to the next sample's
    timestamp_offset; the final sample uses the median gap as a fallback.
    Returns a 5-element list of total seconds, index 0 = Z1 ... index 4 = Z5.
    """
    samples = [
        (s["timestamp_offset"], s[key])
        for s in streams
        if s.get(key) is not None and s.get("timestamp_offset") is not None
    ]
    if len(samples) < 2:
        return [0, 0, 0, 0, 0]

    gaps = [samples[i + 1][0] - samples[i][0] for i in range(len(samples) - 1)]
    fallback = sorted(gaps)[len(gaps) // 2] if gaps else 1
    durations = gaps + [fallback]

    totals = [0, 0, 0, 0, 0]
    for (_, value), dur in zip(samples, durations):
        if dur <= 0:
            continue
        zone_idx = 0
        for i, lo in enumerate(bounds):
            if value >= lo:
                zone_idx = i
        totals[zone_idx] += dur
    return totals


def _format_duration(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def build_zone_chart(
    streams: list[dict],
    key: str,
    bounds: list[int],
    unit: str,
) -> str | None:
    """Build a bar chart of cumulative time spent in each of 5 zones."""
    totals = _time_in_zones(streams, key, bounds)
    if not any(totals):
        return None

    labels = []
    for i, lo in enumerate(bounds):
        hi = bounds[i + 1] - 1 if i + 1 < len(bounds) else None
        labels.append(f"Z{i + 1} ({lo}-{hi})" if hi is not None else f"Z{i + 1} ({lo}+)")
    minutes = [t / 60 for t in totals]
    hover = [_format_duration(t) for t in totals]

    fig = go.Figure(
        go.Bar(
            x=labels,
            y=minutes,
            marker_color=ZONE_COLORS,
            customdata=hover,
            hovertemplate="%{x} " + unit + ": %{customdata}<extra></extra>",
        )
    )
    fig.update_layout(
        xaxis_title="Zone",
        yaxis_title="Time (minutes)",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=280,
        margin=dict(l=50, r=20, t=20, b=50),
        showlegend=False,
    )
    return pio.to_html(fig, full_html=False, include_plotlyjs=False)
