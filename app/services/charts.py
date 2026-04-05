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
