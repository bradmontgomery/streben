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


def _time_in_buckets(streams: list[dict], key: str, bucket_size: int) -> dict[int, int]:
    """Sum sample durations into buckets keyed by bucket lower bound.

    Sample duration is derived from the gap to the next sample's
    timestamp_offset; the final sample uses the median gap as a fallback.
    """
    samples = [
        (s["timestamp_offset"], s[key])
        for s in streams
        if s.get(key) is not None and s.get("timestamp_offset") is not None
    ]
    if len(samples) < 2:
        return {}

    gaps = [samples[i + 1][0] - samples[i][0] for i in range(len(samples) - 1)]
    fallback = sorted(gaps)[len(gaps) // 2] if gaps else 1
    durations = gaps + [fallback]

    buckets: dict[int, int] = {}
    for (_, value), dur in zip(samples, durations):
        if dur <= 0:
            continue
        bucket = int(value // bucket_size) * bucket_size
        buckets[bucket] = buckets.get(bucket, 0) + dur
    return buckets


def _format_duration(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def build_zone_chart(
    streams: list[dict],
    key: str,
    bucket_size: int,
    color: str,
    unit: str,
) -> str | None:
    """Build a bar chart of cumulative time spent in each value bucket."""
    buckets = _time_in_buckets(streams, key, bucket_size)
    if not buckets:
        return None

    lower_bounds = sorted(buckets.keys())
    labels = [f"{lo}-{lo + bucket_size - 1}" for lo in lower_bounds]
    minutes = [buckets[lo] / 60 for lo in lower_bounds]
    hover = [_format_duration(buckets[lo]) for lo in lower_bounds]

    fig = go.Figure(
        go.Bar(
            x=labels,
            y=minutes,
            marker_color=color,
            customdata=hover,
            hovertemplate="%{x} " + unit + ": %{customdata}<extra></extra>",
        )
    )
    fig.update_layout(
        xaxis_title=unit,
        yaxis_title="Time (minutes)",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=280,
        margin=dict(l=50, r=20, t=20, b=50),
        showlegend=False,
    )
    return pio.to_html(fig, full_html=False, include_plotlyjs=False)
