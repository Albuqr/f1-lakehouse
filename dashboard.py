import importlib
import unicodedata
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
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
PARTIAL = "#F1F1F1"  # background of small-multiple panels missing some races
MUTED = "#7A7A7A"
INK = "#222222"
COMPOUNDS = list(PIRELLI)
TABS = ["Stint explorer", "Consistency", "Degradation"]
HEADINGS = {
    "Stint explorer": "One driver's race, stint by stint",
    "Consistency": "How consistent were drivers within a stint?",
    "Degradation": "How quickly did each compound lose pace?",
}
TIE = 0.001  # s/lap: compounds closer than this at a circuit are reported as level
SPREAD_RATIO = 3  # driver spread within a race this many times the circuit spread reads as "barely varies"


def version():
    # cache_data keys on a function's own source, not on analysis.py or the parquet files it reads,
    # so edits there were served stale until restart. Fold their mtimes into the key.
    return tuple(f.stat().st_mtime_ns for f in [Path(analysis.__file__), *Path("data").glob("*.parquet")])


@st.cache_data
def load(version):
    return analysis.load_data()


@st.cache_data
def derived(version):
    fct, dim_driver, dim_session, _, dim_compound = load(version)
    slopes = analysis.stint_fits(fct)
    slopes_raw = analysis.stint_fits(fct, k=0)
    return (
        analysis.pace_trend(slopes, dim_compound, dim_session),
        analysis.consistency(slopes, dim_driver, dim_session),
        slopes,
        analysis.pace_trend(slopes_raw, dim_compound, dim_session),
    )


def fmt_time(s):
    m, sec = divmod(round(s, 1), 60)
    return f"{int(m)}:{sec:04.1f}"


def short(event):
    return event.replace(" Grand Prix", "")


def slug(name):
    # Filenames stay ASCII, so "São Paulo" -> "sao-paulo": decompose accents, then drop the combining marks.
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().replace(" ", "-")


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
# Team colour, plus the line style and marker fastf1 uses to tell teammates apart, resolved at build time.
style = {r.driver_code: dict(color=r.colour, dash="dash" if r.line_style == "dashed" else "solid",
                             symbol="circle" if r.marker == "o" else "x") for r in dim_driver.itertuples()}

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

year = sessions["year"].iat[-1]


@st.dialog(f"Tyre pace in the last {len(sessions)} races of {year}", width="large")
def overview():
    # Every figure here is read from the data or from analysis.py when the dialog opens.
    a = analysis
    excluded = {flag: int(fct[flag].sum()) for flag in ["is_first_lap", "is_in_lap", "is_out_lap", "is_not_green"]}
    fitted = int(fits["slope"].notna().sum())
    both = pace.merge(raw_pace[["compound_key", "session_key", "mean"]], on=["compound_key", "session_key"],
                      suffixes=("", "_raw"))

    def section(title, items):
        st.markdown(f"#### {title}\n" + "\n".join(i if i.startswith("  ") else f"- {i}" for i in items))

    section("The data", [
        f"Public race timing for the last {len(sessions)} races of the {year} season, loaded with FastF1: "
        f"{join(f'{short(r.event_name)} ({r.event_date:%d %b})' for r in sessions.itertuples())}. "
        f"{fct['driver_key'].nunique()} drivers, {len(fct):,} laps.",
        "It holds lap and sector times, tyre compound and age, pit stops and track status. It does not hold fuel "
        "loads, tyre temperatures or pressures, or car setup, so fuel is estimated and temperature effects can't "
        "be separated from wear.",
    ])
    section("Pace laps", [
        f"{int(fct['is_pace_lap'].sum()):,} of {len(fct):,} laps are pace laps, run at racing speed. Excluded, "
        "with some laps falling under more than one rule:",
        f"  - the first lap of the race ({excluded['is_first_lap']}): standing start, not a flying lap;",
        f"  - in-laps ({excluded['is_in_lap']}) and out-laps ({excluded['is_out_lap']}): time lost in the pit lane;",
        f"  - laps not fully under green ({excluded['is_not_green']}): yellow flags, safety car, VSC or red flag "
        "slow the field.",
        f"The first {a.SKIP_LAPS} laps of every stint are also dropped before fitting, while the tyres warm up.",
    ])
    section("Fuel correction", [
        "A car gets lighter as it burns fuel, which makes it faster and hides tyre wear. Each lap time gets "
        f"{a.FUEL_K:g} s added back per kg burned so far, assuming {a.FUEL_KG:g} kg burned evenly over the race.",
        "Both constants are assumptions: real fuel loads aren't public and the time cost per kg varies by circuit. "
        f"Without the correction, {int((both['mean_raw'] < 0).sum())} of {len(both)} compound averages would show "
        "tyres getting faster with age.",
    ])
    section("What the measures mean", [
        "**Stint trend** (s/lap): the slope of a straight line through a stint's fuel-corrected lap times against "
        "tyre age. How much pace the tyre lost per lap. Degradation averages it per compound per circuit.",
        "**Residual scatter** (s): how far a stint's laps sit from that line, as a standard deviation. Low means "
        "repeatable lap to lap, with wear and fuel already taken out. Consistency averages it over a driver's "
        "stints in a race.",
    ])
    section("Thresholds", [
        f"A stint is fitted only with at least {a.MIN_FIT_LAPS} laps left after the drop, so "
        f"{a.SKIP_LAPS + a.MIN_FIT_LAPS} in total. {fitted:,} of {len(fits):,} stints qualify.",
        f"Degradation shows a compound at a circuit only with at least {a.MIN_COMPOUND_STINTS} fitted stints, and "
        f"reports compounds within {TIE:g} s/lap of each other as level.",
        f"Consistency counts a driver in a race only with at least {a.MIN_STINTS} fitted stints, and hatches a "
        f"circuit average built on fewer than {a.MIN_CIRCUIT_DRIVERS} drivers as low confidence.",
    ])


if not st.session_state.get("overview_seen"):  # open once per session, not on every rerun
    st.session_state.overview_seen = True
    overview()

with st.container(horizontal=True, vertical_alignment="center"):
    heading = st.empty()  # filled once the tabs report which one is open
    if st.button("About this data", icon=":material/info:", type="tertiary"):
        overview()
stint_tab, cons_tab, deg_tab = st.tabs(TABS, key="tab", on_change="rerun")
heading.header(HEADINGS[st.session_state.tab])

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
    mean = wide.mean(axis=1)
    full = races == len(race_order)
    # Averages over different numbers of races aren't comparable: rank full coverage, then group the rest.
    order = pd.concat([mean[full].sort_values(),
                       pd.DataFrame({"r": -races, "m": mean})[~full].sort_values(["r", "m"])["m"]]).index
    field = by_circuit.set_index("circuit")["resid_sd"].reindex(race_order)
    abbr = [c[:3].upper() for c in race_order]
    cols = len(race_order)
    rows = -(-len(order) // cols)
    fig = make_subplots(rows=rows, cols=cols, shared_xaxes=True, shared_yaxes=True,
                        subplot_titles=[f"<b>{c}</b>  {mean[c]:.2f}  <span style='color:{MUTED}'>"
                                        f"{races[c]} of {len(race_order)} races</span>" for c in order],
                        vertical_spacing=0.07, horizontal_spacing=0.025)
    for i, c in enumerate(order):
        r, k = divmod(i, cols)
        s = style[c]
        if not full[c]:
            fig.add_shape(type="rect", xref="x domain", yref="y domain", x0=0, x1=1, y0=0, y1=1, layer="below",
                          fillcolor=PARTIAL, line_width=0, row=r + 1, col=k + 1)
        fig.add_scatter(x=abbr, y=field, mode="lines", line=dict(color=CONTEXT, width=2), hoverinfo="skip",
                        showlegend=False, row=r + 1, col=k + 1)
        fig.add_scatter(  # teammates share a colour; fastf1's line style and marker tell them apart
            x=abbr, y=wide.loc[c], customdata=race_order, mode="lines+markers", showlegend=False, connectgaps=False,
            line=dict(color=s["color"], width=2.5, dash=s["dash"]),
            marker=dict(color=s["color"], size=9, symbol=s["symbol"], line=dict(color=OUTLINE, width=0.5)),
            hovertemplate=f"<b>{c}</b> · %{{customdata}}<br>%{{y:.2f}} s<extra></extra>", row=r + 1, col=k + 1,
        )
    fig.update_layout(template="plotly_white", height=175 * rows + 40, margin=dict(t=30, b=10))
    fig.update_yaxes(range=[0, wide.max().max() * 1.1], nticks=4, ticksuffix=" s")
    fig.update_annotations(font=dict(size=13, color=INK))
    st.plotly_chart(fig, key="cons_all_chart")
    st.caption(
        f"One panel per driver, with their average and the number of races it covers. The {int(full.sum())} "
        f"drivers counted at all {len(race_order)} races come first, most consistent first. The "
        f"{int((~full).sum())} shaded panels follow, by races covered and then average: an average over fewer "
        f"races isn't comparable with a full one. Lines join only consecutive races; a gap is a race where the "
        f"driver had fewer than {analysis.MIN_STINTS} fitted stints. Races left to right: {join(race_order)}. "
        f"Grey line: the circuit average. Team colours; teammates are told apart by solid or dashed line and x or "
        f"o marker."
    )

    first, last = by_circuit.iloc[0], by_circuit.iloc[-1]
    between = last.resid_sd - first.resid_sd
    within = cons.groupby("circuit")["resid_sd"].agg(lambda x: x.max() - x.min())  # driver spread at each race
    ratio = within.median() / between
    barely = ratio >= SPREAD_RATIO
    st.subheader("Consistency barely varies by circuit" if barely else "Consistency varies by circuit")
    st.markdown(
        f"Circuit averages span **{between:.2f} s**, from {first.resid_sd:.2f} at {first.circuit} to "
        f"{last.resid_sd:.2f} at {last.circuit}. Within a single race, drivers span **{within.min():.2f} to "
        f"{within.max():.2f} s** (median {within.median():.2f}), about {ratio:.0f} times as much"
        + (": the driver matters far more than the circuit." if barely else ".")
    )
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
    # Same scale as the per-race chart, so the circuit spread is seen against the driver spread.
    fig.update_yaxes(title="Residual scatter (s)", range=[0, cons["resid_sd"].max() * 1.12])
    st.plotly_chart(fig, key="cons_chart", on_select=pick_race, selection_mode="points")
    st.caption(
        "Drawn on the same scale as the per-race chart. "
        + (f"Hatched bars average fewer than {analysis.MIN_CIRCUIT_DRIVERS} drivers: read them as indicative only. "
           if low.any() else "") + "Hover a bar for the drivers behind it; click it to open that race in Per race above."
    )

    thinnest = by_circuit.loc[by_circuit["drivers"].idxmin()]
    # Is the order real? Compare each gap between neighbouring circuits with the standard error of that difference.
    se = cons.groupby("circuit")["resid_sd"].agg(lambda x: x.std() / len(x) ** 0.5).reindex(by_circuit["circuit"])
    gaps = by_circuit["resid_sd"].diff().iloc[1:].to_numpy()
    se_gap = (se.iloc[1:].to_numpy() ** 2 + se.iloc[:-1].to_numpy() ** 2) ** 0.5
    close = gaps < se_gap
    with st.expander("What this shows", expanded=True):
        st.markdown("\n".join(f"- {n}" for n in [
            "This measures scatter around each stint's fitted trend, not raw spread. Raw lap-time spread also "
            "picks up degradation and fuel burn, which are not driver variability.",
            f"Only drivers with at least {analysis.MIN_STINTS} fitted stints in a race are counted, so "
            f"{thinnest.circuit} rests on {int(thinnest.drivers)} drivers against "
            f"{int(by_circuit['drivers'].max())} at the best-covered circuit.",
            (f"{'The' if close.all() else 'Part of the'} order between circuits is not reliable: {'all ' if close.all() else f'{close.sum()} of '}"
             f"{len(gaps)} neighbouring pairs are {gaps[close].min():.3f} to {gaps[close].max():.3f} s apart, less "
             f"than the standard error of their difference ({se_gap[close].min():.3f} to "
             f"{se_gap[close].max():.3f} s)." if close.any() else
             f"Every neighbouring pair of circuits is further apart than the standard error of the difference, "
             f"so the order holds."),
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
    colour = driver.colour
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
    svg = Path("data/tracks") / f"{slug(race['location'])}.svg"
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

