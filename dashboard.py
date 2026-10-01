import importlib
from functools import partial
from pathlib import Path

import fastf1
import fastf1.plotting
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import analysis

# Streamlit re-executes this script but keeps imported modules, so edits to analysis.py
# would otherwise be ignored until restart. Reloading is cheap; the fits are cached separately.
analysis = importlib.reload(analysis)

st.set_page_config(page_title="F1 tyre pace", layout="wide")

PIRELLI = {"SOFT": "#E10600", "MEDIUM": "#FFD100", "HARD": "#FFFFFF"}
OUTLINE = "#222222"
NEUTRAL = "#5A5A5A"  # consistency bars: graphite, so Pirelli colours stay reserved for compounds
CONTEXT = "#D3D3D3"  # drivers not highlighted in the all-races view
THIN = "#BDBDBD"  # circuit averages resting on too few drivers
INK = "#222222"
COMPOUNDS = list(PIRELLI)
TABS = ["Stint explorer", "Consistency", "Degradation"]
TIE = 0.001  # s/lap: compounds closer than this at a circuit are reported as level


def version():
    # cache_data keys on a function's own source, not on analysis.py or the parquet files it reads,
    # so edits there were served stale until restart. Fold their mtimes into the key.
    return tuple(f.stat().st_mtime_ns for f in [Path(analysis.__file__), *Path("data").glob("*.parquet")])


@st.cache_data
def load(version):
    return analysis.load_data()


@st.cache_data
def derived(version):
    # The module's fits take ~1 s each; cache so reruns stay instant.
    fct, dim_driver, dim_session, _, dim_compound = load(version)
    return (
        analysis.pace_trend(fct, dim_compound, dim_session),
        analysis.consistency(fct, dim_driver, dim_session),
        analysis.stint_fits(fct),
        analysis.pace_trend(fct, dim_compound, dim_session, k=0),  # uncorrected, for the fuel note
    )


@st.cache_data
def team_colour(team, year, rnd):
    try:
        fastf1.Cache.enable_cache("ff1_cache")
        return fastf1.plotting.get_team_color(team, fastf1.get_session(year, rnd, "R"), colormap="official")
    except Exception:
        return NEUTRAL  # no cache and no network: card falls back to grey


@st.cache_data
def driver_styles(year, rnd, codes):
    # Team colour, plus the line style and marker fastf1 uses to tell teammates apart.
    styles = {}
    for code in codes:
        try:
            fastf1.Cache.enable_cache("ff1_cache")
            s = fastf1.plotting.get_driver_style(code, ["color", "linestyle", "marker"], fastf1.get_session(year, rnd, "R"),
                                                 colormap="official")
            styles[code] = dict(color=s["color"], dash="dash" if s["linestyle"] == "dashed" else "solid",
                                symbol="circle" if s["marker"] == "o" else "x")
        except Exception:
            styles[code] = dict(color=NEUTRAL, dash="solid", symbol="circle")  # no cache and no network
    return styles


def fmt_time(s):
    m, sec = divmod(round(s, 1), 60)
    return f"{int(m)}:{sec:04.1f}"


def short(event):
    return event.replace(" Grand Prix", "")


def join(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def num(v, f):
    return "—" if np.isnan(v) else format(v, f)


def stint_columns(df):
    return {
        "Laps": df["n"].astype(int),
        "Slope (s/lap)": df["slope"].map(lambda v: num(v, "+.3f")),
        "Std error": df["stderr"].map(lambda v: num(v, ".3f")),
        "Residual SD (s)": df["resid_sd"].map(lambda v: num(v, ".3f")),
    }


def open_stint(stints, key):
    rows = st.session_state[key].selection.rows
    if not rows:
        return
    r = stints.iloc[rows[0]]
    st.session_state.driver = int(r.driver_key)
    st.session_state.race = int(r.session_key)
    st.session_state.focus = (int(r.driver_key), int(r.session_key), int(r.stint))
    st.session_state.tab = "Stint explorer"
    st.session_state.jumps += 1  # new table key, so the row deselects for next time


v = version()
fct, dim_driver, dim_session, dim_team, dim_compound = load(v)
pace, cons, fits, raw_pace = derived(v)
sessions = dim_session.sort_values("round_number")
race_order = [short(e) for e in sessions["event_name"]]
compound_name = dict(zip(dim_compound["compound_key"], dim_compound["compound_name"]))
driver_code = dict(zip(dim_driver["driver_key"], dim_driver["driver_code"]))

st.session_state.setdefault("driver", int(dim_driver.loc[dim_driver["driver_code"] == "VER", "driver_key"].iat[0]))
st.session_state.setdefault("race", int(sessions.loc[sessions["event_name"].str.contains("Qatar"), "session_key"].iat[0]))
st.session_state.setdefault("jumps", 0)

# st.plotly_chart remounts a chart whenever its figure changes and Plotly never animates a first draw,
# so layout.transition can't fire here. CSS animates marks as they mount instead: on load, on tab change
# and when a selection redraws a chart, but not on a rerun that leaves the figure as it was.
st.html("""<style>
@media (prefers-reduced-motion: no-preference) {
  .stPlotlyChart .bars .point path { transform-box: fill-box; transform-origin: bottom; animation: grow-in 400ms ease-out; }
  .stPlotlyChart .bars .point text, .stPlotlyChart .scatterlayer .trace { animation: fade-in 400ms ease-out; }
}
@keyframes grow-in { from { transform: scaleY(0); } }
@keyframes fade-in { from { opacity: 0; } }
</style>""")  # ponytail: grows bars up from their base; negative bars would need transform-origin top

st.title(f"Tyre pace in the last {len(sessions)} races of {sessions['year'].iat[-1]}")
stint_tab, cons_tab, deg_tab = st.tabs(TABS, key="tab", on_change="rerun")

# ---------------------------------------------------------------- Degradation
with deg_tab:
    st.markdown(
        "How many seconds per lap each compound lost as it aged, averaged over every qualifying stint "
        "at each circuit. Click a bar to see the stints behind it."
    )
    pace = pace.assign(circuit=pace["event_name"].map(short))
    pace = pace.assign(i=pace["circuit"].map(race_order.index)).sort_values(["i", "compound_key"])
    if st.toggle("Show as table", key="pace_table"):
        t = pace[["circuit", "compound_name", "mean", "count"]].copy()
        t["mean"] = t["mean"].map("{:+.3f}".format)
        st.dataframe(
            t.rename(columns={"circuit": "Circuit", "compound_name": "Compound", "mean": "Slope (s/lap)", "count": "Stints"}),
            hide_index=True,
        )
        picked = None
    else:
        # Numeric x so each circuit only reserves slots for the compounds it ran: thick bars,
        # tight within a circuit, wide gaps between circuits.
        w, inner = 0.3, 0.03
        slot = pace.groupby("i").cumcount() - (pace.groupby("i")["i"].transform("size") - 1) / 2
        pace["x"] = pace["i"] + slot * (w + inner)
        lo, hi = min(0, pace["mean"].min()), max(0, pace["mean"].max())
        pad = (hi - lo) * 0.18  # room for the two-line label above the tallest bar
        fig = go.Figure()
        for comp in COMPOUNDS:
            d = pace[pace["compound_name"] == comp]
            fig.add_bar(
                x=d["x"], y=d["mean"], width=w, name=comp,
                marker=dict(color=PIRELLI[comp], line=dict(color=OUTLINE, width=1.5)),
                text=[f"<b>{m:+.3f}</b><br>{n} stints" for m, n in zip(d["mean"], d["count"])],
                textposition="outside", textfont=dict(color=INK, size=13), cliponaxis=False,
                customdata=d[["count", "compound_key", "session_key", "circuit"]],
                hovertemplate=f"<b>%{{customdata[3]}} · {comp}</b><br>%{{y:+.3f}} s/lap<br>"
                              "Average of <b>%{customdata[0]} stints</b><extra></extra>",
            )
        fig.update_layout(
            template="plotly_white", height=620, margin=dict(t=20),
            legend=dict(title_text="Compound"),
        )
        fig.update_xaxes(tickvals=list(range(len(race_order))), ticktext=race_order, showgrid=False,
                         range=[-0.6, len(race_order) - 0.4], tickfont=dict(size=14))
        fig.update_yaxes(title="Pace trend (s/lap)", tickformat="+.2f", zeroline=True, zerolinecolor=OUTLINE,
                         range=[lo - (pad if lo < 0 else 0), hi + pad])
        event = st.plotly_chart(fig, key="deg_chart", on_select="rerun", selection_mode="points")
        picked = event.selection.points[0] if event.selection.points else None

    if picked:
        cd = picked["customdata"]  # selection returns customdata as strings
        ck, sk, circuit = int(cd[1]), int(cd[2]), cd[3]
        behind = (
            fits[(fits["compound_key"] == ck) & (fits["session_key"] == sk) & fits["slope"].notna()]
            .sort_values("slope", ascending=False).reset_index(drop=True)
        )
        st.subheader(f"The {len(behind)} stints behind {circuit} {compound_name[ck].lower()} ({picked['y']:+.3f} s/lap)")
        table = behind.assign(Driver=behind["driver_key"].map(driver_code), Stint=behind["stint"], **stint_columns(behind))
        key = f"deg_stints_{st.session_state.jumps}"
        st.dataframe(
            table[["Driver", "Stint", "Laps", "Slope (s/lap)", "Std error", "Residual SD (s)"]],
            hide_index=True, key=key, on_select=partial(open_stint, behind, key), selection_mode="single-row",
        )
        st.caption("Select a row to open that stint in the stint explorer.")

    # Every figure below is read from pace_trend at render time.
    notes = []
    neg = pace[pace["mean"] <= 0]
    notes.append("All circuit averages are positive after fuel correction." if neg.empty else
                 f"{join(neg['circuit'] + ' ' + neg['compound_name'].str.lower())} "
                 f"{'is' if len(neg) == 1 else 'are'} still negative after fuel correction.")

    order = {}
    for c in race_order:
        g = pace[pace["circuit"] == c]  # softest first
        if len(g) < 2:
            continue
        step = g["mean"].diff().dropna()  # harder minus softer
        order[c] = ("level" if (step.abs() < TIE).all() else "softer" if (step <= -TIE).all()
                    else "harder" if (step >= TIE).all() else "mixed", g)
    softer = [c for c, (k, _) in order.items() if k == "softer"]
    if softer:
        gaps = [f"{g['mean'].iat[0] - g['mean'].iat[-1]:.3f}" for k, g in order.values() if k == "softer"]
        notes.append(f"Softer compounds degrade faster than harder ones at {len(softer)} of the {len(order)} "
                     f"circuits: {join(softer)}, by {join(gaps)} s/lap{' respectively' if len(softer) > 1 else ''}.")
    for c, (k, g) in order.items():
        names, vals = join(g["compound_name"].str.lower()), join(g["mean"].map("{:+.3f}".format))
        if k == "level":
            notes.append(f"At {c} the {names} are within {TIE:g} s/lap of each other ({vals}), so there is no ordering.")
        elif k == "harder":
            notes.append(f"At {c} the order reverses: the {g['compound_name'].iat[-1].lower()} degrades faster than "
                         f"the {g['compound_name'].iat[0].lower()} ({vals}), "
                         f"by {g['mean'].iat[-1] - g['mean'].iat[0]:.3f} s/lap.")
        elif k == "mixed":
            notes.append(f"At {c} the {names} show no consistent ordering ({vals}).")

    top, flat = pace.loc[pace["mean"].idxmax()], pace.loc[pace["mean"].idxmin()]
    notes.append(f"{top['circuit']} {top['compound_name'].lower()} is the hardest on its tyres at {top['mean']:+.3f} "
                 f"s/lap, from {top['count']} stints. {flat['circuit']} {flat['compound_name'].lower()} is the "
                 f"flattest, at {flat['mean']:+.3f}.")
    notes.append(f"Lap times are corrected by adding back {analysis.FUEL_K:g} s/kg × fuel burned, estimated as "
                 f"{analysis.FUEL_KG:g} kg over the race distance.")
    both = pace.merge(raw_pace[["compound_key", "session_key", "mean"]], on=["compound_key", "session_key"],
                      suffixes=("", "_raw"))
    shift = both["mean"] - both["mean_raw"]
    went_neg = both[both["mean_raw"] < 0]
    note = f"Without that correction every average is {shift.min():.3f} to {shift.max():.3f} s/lap lower"
    if len(went_neg):
        note += (f", and {len(went_neg)} of {len(both)} turn negative "
                 f"({join(went_neg['circuit'] + ' ' + went_neg['compound_name'].str.lower())}), "
                 "which would have claimed tyres improve with age")
    notes.append(note + ".")
    notes.append("Real fuel loads are not in public timing data, so this is an assumption.")
    with st.expander("What this shows", expanded=True):
        st.markdown("\n".join(f"- {n}" for n in notes))

# ---------------------------------------------------------------- Consistency
with cons_tab:
    st.markdown(
        "How far each driver's laps scatter around their own stint trend: one race at a time, then each driver "
        "across all races, then the circuit averages they add up to."
    )
    cons = cons.assign(circuit=cons["event_name"].map(short))
    race_info = sessions.assign(circuit=sessions["event_name"].map(short)).set_index("circuit")

    def styles_at(circuit, codes):
        r = race_info.loc[circuit]
        return driver_styles(int(r["year"]), int(r["round_number"]), tuple(codes))

    def roster(g):
        g = g.sort_values("resid_sd")
        cells = [f"{c} {v:.2f}" for c, v in zip(g["driver_code"], g["resid_sd"])]
        return "<br>".join("   ".join(cells[i:i + 4]) for i in range(0, len(cells), 4))

    by_circuit = (
        cons.groupby("circuit")
        .apply(lambda g: pd.Series({"resid_sd": g["resid_sd"].mean(), "drivers": len(g), "roster": roster(g)}),
               include_groups=False)
        .sort_values("resid_sd").reset_index()
    )
    st.session_state.setdefault("cons_race", by_circuit["circuit"].iat[0])

    st.subheader("Per race")
    circuit = st.segmented_control("Race", [c for c in race_order if c in set(cons["circuit"])],
                                   key="cons_race", required=True)
    drivers = cons[cons["circuit"] == circuit].sort_values("resid_sd")
    style = styles_at(circuit, drivers["driver_code"])
    avg = drivers["resid_sd"].mean()
    fig = go.Figure(go.Bar(
        x=drivers["driver_code"], y=drivers["resid_sd"],
        text=drivers["resid_sd"].map("{:.2f}".format), textposition="outside", cliponaxis=False,
        textfont=dict(color=INK), customdata=drivers[["n"]],
        marker=dict(color=[style[c]["color"] for c in drivers["driver_code"]], line=dict(color=OUTLINE, width=1)),
        hovertemplate="<b>%{x}</b><br>%{y:.2f} s over %{customdata[0]} laps<extra></extra>",
    ))
    fig.add_hline(y=avg, line_dash="dash", line_color=OUTLINE, layer="below",
                  annotation_text=f"Circuit average {avg:.2f}", annotation_position="top left")
    # Shared scale across races, so switching races compares like with like.
    fig.update_layout(template="plotly_white", margin=dict(t=20), height=360)
    fig.update_xaxes(tickfont=dict(size=13, color=INK))
    fig.update_yaxes(title="Residual scatter (s)", range=[0, cons["resid_sd"].max() * 1.12])
    st.plotly_chart(fig, key="cons_race_chart")
    st.caption(f"{len(drivers)} drivers at {circuit}, most consistent on the left, in team colours.")

    st.subheader("All races")
    wide = cons.pivot_table(index="driver_code", columns="circuit", values="resid_sd").reindex(columns=race_order)
    races = wide.notna().sum(axis=1)
    ranked = wide[races >= races.median()].mean(axis=1).sort_values()
    best, worst = list(ranked.index[:2]), list(ranked.index[-2:])
    codes = sorted(wide.index)
    latest = cons.sort_values("session_key").groupby("driver_code")["circuit"].last()  # each driver's latest team
    style = {c: styles_at(latest[c], [c])[c] for c in codes}
    fig = go.Figure()
    # Grey context: every driver in one trace, broken between drivers.
    fig.add_scatter(
        x=[x for _ in codes for x in [*race_order, None]], y=[y for c in codes for y in [*wide.loc[c], None]],
        text=[c for c in codes for _ in range(len(race_order) + 1)], mode="lines+markers", showlegend=False,
        line=dict(color=CONTEXT, width=1), marker=dict(color=CONTEXT, size=6),
        hovertemplate="%{text} · %{x}<br>%{y:.2f} s<extra></extra>",
    )
    for c in codes:  # teammates share a colour; fastf1's line style and marker tell them apart
        s = style[c]
        fig.add_scatter(
            x=race_order, y=wide.loc[c], name=c, mode="lines+markers",
            visible=True if c in best + worst else "legendonly",
            line=dict(color=s["color"], width=2.5, dash=s["dash"]),
            marker=dict(color=s["color"], size=10, symbol=s["symbol"], line=dict(color=s["color"], width=1)),
            hovertemplate=f"<b>{c}</b> · %{{x}}<br>%{{y:.2f}} s<extra></extra>",
        )
    fig.update_layout(template="plotly_white", margin=dict(t=20), height=480,
                      legend=dict(title_text="Driver"))
    fig.update_yaxes(title="Residual scatter (s)", rangemode="tozero")
    st.plotly_chart(fig, key="cons_all_chart")
    st.caption(
        f"Highlighted by default: {join(best)}, the most consistent, and {join(worst)}, the least, among drivers "
        f"counted at {races.median():g} or more of the {len(race_order)} races. Team colours; teammates are told "
        f"apart by solid or dashed line and x or o marker. Click a driver in the legend to add or remove them; "
        f"double-click to isolate one. Gaps are races where a driver had fewer than {analysis.MIN_DRIVER_LAPS} "
        f"fitted laps."
    )

    st.subheader("Circuit average")
    low = by_circuit["drivers"] < analysis.MIN_CIRCUIT_DRIVERS

    def pick_race():
        pts = st.session_state.cons_chart.selection.points
        if pts:
            st.session_state.cons_race = pts[0]["x"]

    fig = go.Figure(go.Bar(
        x=by_circuit["circuit"], y=by_circuit["resid_sd"],
        text=[f"<b>{v:.2f}</b><br>{int(n)} drivers" + ("<br><i>low confidence</i>" if thin else "")
              for v, n, thin in zip(by_circuit["resid_sd"], by_circuit["drivers"], low)],
        textposition="outside", cliponaxis=False, textfont=dict(color=INK, size=13),
        customdata=by_circuit[["drivers", "roster"]],
        marker=dict(color=[THIN if thin else NEUTRAL for thin in low], line=dict(color=OUTLINE, width=1.5),
                    pattern=dict(shape=["/" if thin else "" for thin in low], fgcolor=NEUTRAL, solidity=0.25)),
        hovertemplate="<b>%{x}</b>: %{y:.2f} s, average of %{customdata[0]} drivers<br><br>%{customdata[1]}<extra></extra>",
    ))
    fig.update_layout(template="plotly_white", margin=dict(t=20), hoverlabel=dict(font_family="monospace"))
    fig.update_yaxes(title="Residual scatter (s)", range=[0, by_circuit["resid_sd"].max() * 1.25])
    st.plotly_chart(fig, key="cons_chart", on_select=pick_race, selection_mode="points")
    st.caption(
        (f"Hatched bars average fewer than {analysis.MIN_CIRCUIT_DRIVERS} drivers: read them as indicative only. "
         if low.any() else "") + "Hover a bar for the drivers behind it; click it to open that race in Per race above."
    )

    first, last = by_circuit.iloc[0], by_circuit.iloc[-1]
    thinnest = by_circuit.loc[by_circuit["drivers"].idxmin()]
    with st.expander("What this shows", expanded=True):
        st.markdown("\n".join(f"- {n}" for n in [
            "This measures scatter around each stint's fitted trend, not raw spread. Raw lap-time spread also "
            "picks up degradation and fuel burn, which are not driver variability.",
            f"Circuit averages run from {first.resid_sd:.2f} s at {first.circuit} to {last.resid_sd:.2f} s "
            f"at {last.circuit}.",
            f"Only drivers with at least {analysis.MIN_DRIVER_LAPS} fitted laps in a race are counted, so "
            f"{thinnest.circuit} rests on {int(thinnest.drivers)} drivers against "
            f"{int(by_circuit['drivers'].max())} at the best-covered circuit.",
            "The ranking is not stable. A small change to how stints are trimmed before fitting reordered the "
            "circuits, so treat the order as provisional.",
        ]))

# ---------------------------------------------------------------- Stint explorer
with stint_tab:
    st.markdown(
        "One driver's lap times in one race, against tyre age, with the trend fitted to each stint. "
        "Click a stint in the legend to isolate it."
    )
    raced = dim_driver[dim_driver["driver_key"].isin(fct["driver_key"].unique())].sort_values("driver_name")
    driver_label = {r.driver_key: f"{r.driver_name} ({r.driver_code})" for r in raced.itertuples()}
    session_label = dict(zip(sessions["session_key"], sessions["event_name"]))

    with st.container(horizontal=True):
        driver_key = st.selectbox("Driver", list(driver_label), key="driver", format_func=driver_label.get, width=260)
        session_key = st.selectbox("Race", list(session_label), key="race", format_func=session_label.get, width=260)
        mode = st.segmented_control("Lap time", ["Fuel-corrected", "Raw"], default="Fuel-corrected", required=True,
                                key="lap_mode")

    driver = dim_driver.set_index("driver_key").loc[driver_key]
    race = sessions.set_index("session_key").loc[session_key]
    laps_here = fct[(fct["driver_key"] == driver_key) & (fct["session_key"] == session_key)]
    team_key = (laps_here if len(laps_here) else fct[fct["driver_key"] == driver_key])["team_key"].iat[-1]
    team = dim_team.set_index("team_key").loc[team_key, "team_name"]
    colour = team_colour(team, int(race["year"]), int(race["round_number"]))
    r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
    ink = "#111111" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "#FFFFFF"

    card, name, track = st.columns([1, 1.1, 1.6], vertical_alignment="center")
    card.html(
        f'<div style="background:{colour};color:{ink};border-radius:10px;padding:22px 26px">'
        f'<div style="font-size:3.4rem;font-weight:800;line-height:1;letter-spacing:.02em">{driver.driver_code}</div>'
        f'<div style="font-size:1.6rem;font-weight:700;margin-top:6px">#{driver.driver_number}</div>'
        f'<div style="font-size:1.05rem;margin-top:10px">{team}</div></div>'
    )
    name.subheader(race["event_name"])
    name.caption(f"{race['location']} · Round {race['round_number']} · {race['event_date']:%d %b %Y}")
    svg = Path("data/tracks") / f"{race['location'].lower().replace(' ', '-')}.svg"
    if svg.exists():
        track.image(svg.read_text(encoding="utf-8"), width=340)

    sel = fits[(fits["driver_key"] == driver_key) & (fits["session_key"] == session_key)].sort_values("stint")
    focus = st.session_state.get("focus")
    focus_stint = focus[2] if focus and focus[:2] == (driver_key, session_key) else None
    corrected = mode == "Fuel-corrected"

    if sel.empty:
        st.info("No pace laps for this driver in this race.")
    else:
        fig = go.Figure()
        ymin, ymax = np.inf, -np.inf
        for s in sel.itertuples():
            laps = analysis.stint_laps(fct, driver_key, session_key, s.stint)
            comp = compound_name[s.compound_key]
            x = laps["tyre_life"].astype(float)
            y = laps["lap_time_corrected" if corrected else "lap_time_s"]
            ymin, ymax = min(ymin, y.min()), max(ymax, y.max())
            group = dict(legendgroup=f"s{s.stint}",
                         visible="legendonly" if focus_stint not in (None, s.stint) else True)
            hover = [
                f"Lap {int(l)}<br>Tyre age {int(a)}<br>Raw {fmt_time(rt)}<br>Corrected {fmt_time(ct)}<br>{comp}"
                for l, a, rt, ct in zip(laps["lap_number"], x, laps["lap_time_s"], laps["lap_time_corrected"])
            ]
            fig.add_scatter(
                x=x, y=y, mode="markers", name=f"Stint {s.stint} · {comp}", **group,
                marker=dict(color=PIRELLI[comp], size=8, line=dict(color=OUTLINE, width=1)),
                text=hover, hovertemplate="%{text}<extra></extra>",
            )
            if np.isnan(s.slope) or not corrected:
                continue  # the module fits corrected times only, and only stints long enough
            # The module's own line, over the laps it fitted (it drops each stint's first SKIP_LAPS).
            fx = x.iloc[analysis.SKIP_LAPS:].agg(["min", "max"])
            fit = s.intercept + s.slope * fx
            fig.add_scatter(x=fx, y=fit, mode="lines", hoverinfo="skip", showlegend=False, **group,
                            line=dict(color=OUTLINE, width=4))
            fig.add_scatter(
                x=fx, y=fit, mode="lines", showlegend=False, **group, line=dict(color=PIRELLI[comp], width=2),
                hovertemplate=f"Stint {s.stint} fit<br>{s.slope:+.3f} s/lap<br>R² {s.r ** 2:.2f}<extra></extra>",
            )
        step = 0.5 if ymax - ymin <= 6 else 1 if ymax - ymin <= 12 else 2
        ticks = np.arange(np.floor(ymin / step) * step, ymax + step, step)
        fig.update_layout(
            template="plotly_white", height=560, margin=dict(t=30),
            xaxis=dict(title="Tyre age (laps)"),
            yaxis=dict(title=f"{mode} lap time", tickvals=ticks, ticktext=[fmt_time(t) for t in ticks]),
            legend=dict(orientation="h", y=1.06, itemclick="toggleothers", itemdoubleclick="toggle"),
        )
        st.plotly_chart(fig, key="stint_chart")
        if not corrected:
            st.caption("Raw times include fuel burn, so they fall as the tank empties. "
                       "Fitted lines are drawn on fuel-corrected times only.")

        circuit_avg = sel.merge(pace, on=["compound_key", "session_key"], how="left")["mean"]
        table = sel.assign(Stint=sel["stint"], Compound=sel["compound_key"].map(compound_name), **stint_columns(sel),
                           **{"Circuit average": circuit_avg.map(lambda v: num(v, "+.3f")).values})
        st.dataframe(table[["Stint", "Compound", "Laps", "Slope (s/lap)", "Circuit average", "Std error",
                            "Residual SD (s)"]], hide_index=True)
        st.caption(
            "Illustration, not evidence. One driver's stints cannot establish the findings in the Degradation and "
            f"Consistency tabs. Fits skip each stint's first {analysis.SKIP_LAPS} laps, so stints under "
            f"{analysis.SKIP_LAPS + analysis.MIN_FIT_LAPS} laps are shown without one. Circuit average is that "
            "compound's mean slope at this race; single stints often sit well either side of it."
        )

st.divider()
st.caption("Circuit layouts © 2024–2026 Jules Roy, github.com/julesr0y/f1-circuits-svg, CC BY 4.0.")

