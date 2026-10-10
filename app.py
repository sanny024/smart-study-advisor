"""
app.py - THE USER INTERFACE (Streamlit)
=======================================
This file only shows data and collects input. All reasoning lives in the other modules:
  knowledge_base.py -> facts, thresholds, validation
  rules.py          -> the IF-THEN rule base
  inference_engine.py -> forward chaining, conflict resolution, backward chaining
  study_planner.py  -> study-time allocation
Run with:  streamlit run app.py
"""
from __future__ import annotations

import html

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import explanation
from advisor import run_advisor
from inference_engine import BackwardChainer
from knowledge_base import (DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS, MAX_DAILY_HOURS, MIN_DAILY_HOURS,
                            SAMPLE_SUBJECTS, THRESHOLD_DESCRIPTIONS, KnowledgeBase,
                            validate_daily_hours, validate_subject_list)
from recommendations import next_action
from reports import (build_html_summary, build_json_text, build_text_summary, plan_dataframe,
                     plan_to_csv, timetable_dataframe)
from rules import CONFLICT_STRATEGY_TEXT, LIMITATIONS, STAGES, build_rules
from study_planner import minutes_text
from ui_styles import (CSS, INDIGO, PRIORITY_BG, PRIORITY_COLORS, PRIORITY_FG)

PAGES = ["Dashboard", "Student Inputs", "Recommendations", "Study Planner",
         "Knowledge Base & Rules", "Reasoning Trace", "Reports"]
COLUMNS = ["Subject", "Marks (%)", "Days left", "Difficulty", "Confidence (1-5)"]

st.set_page_config(page_title="Smart Study Advisor", page_icon="🎓", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def esc(text) -> str:
    return html.escape(str(text))


def badge(level: str) -> str:
    return (f'<span class="ssa-badge" style="background:{PRIORITY_BG[level]};color:{PRIORITY_FG[level]}">'
            f'{esc(level.capitalize())} priority</span>')


def kpi(label: str, value: str, hint: str = "", teal: bool = False) -> str:
    return (f'<div class="ssa-kpi{" teal" if teal else ""}"><div class="label">{esc(label)}</div>'
            f'<div class="value">{esc(value)}</div><div class="hint">{esc(hint)}</div></div>')


def page_header(title: str, subtitle: str) -> None:
    st.markdown(f'<h2 class="ssa-page-title">{esc(title)}</h2><div class="ssa-page-sub">{esc(subtitle)}</div>',
                unsafe_allow_html=True)


def style_figure(fig, height: int = 340):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#1E1B4B"),
                      legend=dict(orientation="h", y=-0.2))
    return fig


def sample_dataframe() -> pd.DataFrame:
    return pd.DataFrame({
        "Subject": [s["name"] for s in SAMPLE_SUBJECTS],
        "Marks (%)": [float(s["marks"]) for s in SAMPLE_SUBJECTS],
        "Days left": pd.array([s["days_left"] for s in SAMPLE_SUBJECTS], dtype="Int64"),
        "Difficulty": [s["difficulty"].capitalize() for s in SAMPLE_SUBJECTS],
        "Confidence (1-5)": pd.array([s["confidence"] for s in SAMPLE_SUBJECTS], dtype="Int64"),
    })


def empty_dataframe() -> pd.DataFrame:
    return pd.DataFrame({"Subject": pd.Series(dtype="str"), "Marks (%)": pd.Series(dtype="float"),
                         "Days left": pd.array([], dtype="Int64"), "Difficulty": pd.Series(dtype="str"),
                         "Confidence (1-5)": pd.array([], dtype="Int64")})


def dataframe_to_rows(df: pd.DataFrame) -> list[dict]:
    rows = []
    for _, r in df.iterrows():
        rows.append({"name": r.get("Subject"), "marks": r.get("Marks (%)"), "days_left": r.get("Days left"),
                     "difficulty": r.get("Difficulty"), "confidence": r.get("Confidence (1-5)")})
    return rows


# --------------------------------------------------------------------------
# Session state
# --------------------------------------------------------------------------
def init_state() -> None:
    ss = st.session_state
    if "initialised" in ss:
        return
    ss.initialised = True
    ss.student_name = ""
    ss.daily_hours = 4.0
    ss.base_df = sample_dataframe()
    ss.edited_df = ss.base_df.copy()
    ss.editor_version = 0
    ss.thresholds = dict(DEFAULT_THRESHOLDS)
    ss.weights = dict(DEFAULT_WEIGHTS)
    ss.block_minutes = 15
    ss.last_page = None


def compute_output():
    """Run validation and the whole advisor pipeline. Returns (output or None, error list)."""
    ss = st.session_state
    try:
        kb = KnowledgeBase(ss.thresholds, ss.weights)
    except ValueError as exc:
        return None, [str(exc)]
    subjects, errors = validate_subject_list(dataframe_to_rows(ss.edited_df))
    hours, hour_errors = validate_daily_hours(ss.daily_hours)
    errors = errors + hour_errors
    if errors:
        return None, errors
    return run_advisor(ss.student_name, subjects, hours, kb, block_minutes=ss.block_minutes), []


def require_output():
    """Stop the page with a friendly message unless there is valid, non-empty data."""
    output, errors = compute_output()
    if errors:
        st.error("Please fix these input problems on the 'Student Inputs' page:")
        for message in errors:
            st.markdown(f"- {message}")
        st.stop()
    if not output.subjects:
        st.markdown('<div class="ssa-empty"><b>No subjects yet</b><br>Open <b>Student Inputs</b> and add at '
                    'least one subject, or load the sample data.</div>', unsafe_allow_html=True)
        st.stop()
    return output


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
def page_dashboard():
    st.markdown("""<div class="ssa-hero"><h1>Smart Study Advisor</h1>
    <p>A rule-based Knowledge Representation and Reasoning (KRR) system. It stores your marks, deadlines and
    difficulty as facts, applies explicit IF-THEN rules, and explains which study priorities follow and why.</p></div>""",
                unsafe_allow_html=True)
    out = require_output()
    results = out.results
    avg = sum(r.subject.marks for r in results) / len(results)
    high = sum(1 for r in results if r.final_priority == "high")
    cols = st.columns(4)
    cols[0].markdown(kpi("Subjects", str(len(results)), "entered by you"), unsafe_allow_html=True)
    cols[1].markdown(kpi("Average marks", f"{avg:.1f}%", "across all subjects"), unsafe_allow_html=True)
    cols[2].markdown(kpi("High priority", str(high), "inferred by the rules", teal=True), unsafe_allow_html=True)
    cols[3].markdown(kpi("Daily study time", minutes_text(out.summary.available_minutes), "available per day", teal=True),
                     unsafe_allow_html=True)
    st.write("")

    left, right = st.columns([3, 2])
    df = pd.DataFrame({"Subject": [r.name for r in results], "Marks": [r.subject.marks for r in results],
                       "Priority": [r.final_priority.capitalize() for r in results]})
    with left:
        with st.container(border=True):
            fig = px.bar(df, x="Subject", y="Marks", color="Priority", title="Subject performance",
                         color_discrete_map={k.capitalize(): v for k, v in PRIORITY_COLORS.items()},
                         range_y=[0, 100])
            fig.add_hline(y=out.kb.thresholds["low_marks"], line_dash="dot", line_color="#6B7280",
                          annotation_text="low-marks threshold")
            st.plotly_chart(style_figure(fig), use_container_width=True)
    with right:
        with st.container(border=True):
            counts = df["Priority"].value_counts()
            fig = go.Figure(go.Pie(labels=list(counts.index), values=list(counts.values), hole=0.6,
                                   marker=dict(colors=[PRIORITY_COLORS[p.lower()] for p in counts.index])))
            fig.update_layout(title="Priority distribution")
            st.plotly_chart(style_figure(fig), use_container_width=True)

    st.markdown("#### Upcoming examinations")
    upcoming = sorted(out.recommendations, key=lambda r: (r.days_left, r.subject.casefold()))
    table = pd.DataFrame({"Subject": [r.subject for r in upcoming], "Days left": [r.days_left for r in upcoming],
                          "Urgency": [r.urgency.capitalize() for r in upcoming],
                          "Priority": [r.priority.capitalize() for r in upcoming]})
    st.dataframe(table, hide_index=True, use_container_width=True)
    st.markdown("#### Recommended next action")
    st.markdown(f'<div class="ssa-action">{esc(next_action(out.recommendations))}</div>', unsafe_allow_html=True)


def page_inputs():
    ss = st.session_state
    page_header("Student Profile and Academic Inputs",
                "Enter your own subjects, or start from the clearly labelled sample data.")

    def set_name():
        ss.student_name = ss.w_name

    def set_hours():
        ss.daily_hours = ss.w_hours

    c1, c2 = st.columns(2)
    c1.text_input("Student name (optional)", value=ss.student_name, key="w_name", on_change=set_name,
                  max_chars=60)
    c2.number_input("Daily available study hours", min_value=0.0, max_value=24.0, step=0.25,
                    value=float(ss.daily_hours), key="w_hours", on_change=set_hours,
                    help=f"Allowed range: {MIN_DAILY_HOURS:g} to {MAX_DAILY_HOURS:g} hours.")

    def load_sample():
        ss.base_df = sample_dataframe()
        ss.edited_df = ss.base_df.copy()
        ss.editor_version += 1

    def clear_all():
        ss.base_df = empty_dataframe()
        ss.edited_df = ss.base_df.copy()
        ss.editor_version += 1

    b1, b2, _ = st.columns([1, 1, 3])
    b1.button("Load sample data", on_click=load_sample, use_container_width=True)
    b2.button("Clear all subjects", on_click=clear_all, use_container_width=True)
    st.caption("The table below starts with SAMPLE data for demonstration. Edit any cell, use the + row at the "
               "bottom to add a subject, or select a row and press Delete to remove it.")

    edited = st.data_editor(
        ss.base_df, key=f"editor_{ss.editor_version}", num_rows="dynamic", hide_index=True,
        use_container_width=True,
        column_config={
            "Subject": st.column_config.TextColumn("Subject", max_chars=60, required=True),
            "Marks (%)": st.column_config.NumberColumn("Marks (%)", min_value=0.0, max_value=100.0, step=0.5,
                                                       required=True),
            "Days left": st.column_config.NumberColumn("Days left", min_value=0, max_value=365, step=1,
                                                       required=True),
            "Difficulty": st.column_config.SelectboxColumn("Difficulty", options=["Low", "Medium", "High"],
                                                           required=True),
            "Confidence (1-5)": st.column_config.NumberColumn("Confidence (1-5)", min_value=1, max_value=5, step=1,
                                                              help="Optional. 1 = very unsure, 5 = very confident."),
        })
    ss.edited_df = edited

    subjects, errors = validate_subject_list(dataframe_to_rows(edited))
    _, hour_errors = validate_daily_hours(ss.daily_hours)
    errors = errors + hour_errors
    if errors:
        st.error("Some inputs need attention:")
        for message in errors:
            st.markdown(f"- {message}")
    elif not subjects:
        st.markdown('<div class="ssa-empty">Your subject list is empty. Add a row to begin.</div>',
                    unsafe_allow_html=True)
    else:
        st.success(f"All inputs are valid: {len(subjects)} subject(s), {ss.daily_hours:g} study hours per day. "
                   "Open another page to see the results.")


def page_recommendations():
    page_header("Intelligent Study Recommendations",
                "Every priority below was inferred by the rule engine from your facts.")
    out = require_output()
    chosen = st.multiselect("Show priorities", ["High", "Medium", "Low"], default=["High", "Medium", "Low"])
    shown = [r for r in out.recommendations if r.priority.capitalize() in chosen]
    if not shown:
        st.info("No subjects match the selected priorities.")
    for rec in shown:
        with st.container(border=True):
            st.markdown(f'<div class="ssa-rec-title">{esc(rec.subject)} &nbsp; {badge(rec.priority)}</div>'
                        f'<div class="ssa-meta">Marks {rec.marks}% &middot; exam in {rec.days_left} day(s) &middot; '
                        f'{esc(rec.difficulty)} difficulty &middot; suggested time '
                        f'<b>{esc(rec.daily_time_text)}</b> per day</div>', unsafe_allow_html=True)
            if rec.urgency_warning:
                (st.error if rec.urgency in ("critical", "urgent") else st.warning)(rec.urgency_warning)
            st.markdown("**Revision strategy:** " + rec.strategy)
            st.markdown("**Revision recommendations:**")
            for step in rec.revision_steps:
                st.markdown(f"- {step}")
            with st.expander("Why this priority? (rules that fired)"):
                for reason in rec.reasons:
                    st.markdown(f"- {reason}")
                st.caption(out.result_for(rec.subject).explanation)


def page_planner():
    ss = st.session_state
    page_header("Personalized Study Planner",
                "Your daily study time shared across subjects by inferred priority.")
    st.info("This schedule is an advisory plan. Adjust it to your energy, classes and commitments.")
    out = require_output()

    with st.expander("Adjust the planner (optional)"):
        with st.form("planner_form"):
            w1, w2, w3, w4 = st.columns(4)
            high = w1.number_input("High weight", 0.0, 20.0, float(ss.weights["high"]), 0.5)
            med = w2.number_input("Medium weight", 0.0, 20.0, float(ss.weights["medium"]), 0.5)
            low = w3.number_input("Low weight", 0.0, 20.0, float(ss.weights["low"]), 0.5)
            block = w4.selectbox("Block size (minutes)", [15, 30], index=[15, 30].index(ss.block_minutes))
            if st.form_submit_button("Apply"):
                ss.weights = {"high": high, "medium": med, "low": low}
                ss.block_minutes = block
                st.rerun()
        st.caption("Weights decide each subject's share. Time is handed out in whole blocks, so totals never "
                   "exceed your daily limit.")

    s = out.summary
    k = st.columns(3)
    k[0].markdown(kpi("Available", minutes_text(s.available_minutes), "per day"), unsafe_allow_html=True)
    k[1].markdown(kpi("Allocated", minutes_text(s.allocated_minutes), "sum of all subjects", teal=True),
                  unsafe_allow_html=True)
    k[2].markdown(kpi("Left free", minutes_text(s.unallocated_minutes),
                      "balanced" if s.balanced else "rounding discrepancy"), unsafe_allow_html=True)
    st.write("")
    for note in s.notes:
        st.warning(note)

    tab_today, tab_week = st.tabs(["Today's plan", "Multi-day timetable"])
    with tab_today:
        df = plan_dataframe(out)
        st.dataframe(df[["Subject", "Priority", "Urgency", "Days left", "Share (%)", "Study minutes per day",
                         "Study time"]], hide_index=True, use_container_width=True,
                     column_config={"Share (%)": st.column_config.ProgressColumn("Share (%)", min_value=0,
                                                                                 max_value=100, format="%.1f%%")})
        fig = px.bar(df, x="Study minutes per day", y="Subject", color="Priority", orientation="h",
                     color_discrete_map={k.capitalize(): v for k, v in PRIORITY_COLORS.items()},
                     title="Minutes per subject today")
        fig.update_yaxes(categoryorder="total ascending")
        st.plotly_chart(style_figure(fig), use_container_width=True)
    with tab_week:
        tt = timetable_dataframe(out)
        st.caption("A subject is studied only until its exam day. On the exam day it gets a lighter revision slot.")
        pivot = tt.pivot_table(index="Day", columns="Subject", values="Minutes", aggfunc="sum",
                               fill_value=0, sort=False)
        st.dataframe(pivot, use_container_width=True)
        fig = px.bar(tt, x="Day", y="Minutes", color="Subject", title="Study minutes per day")
        st.plotly_chart(style_figure(fig, 380), use_container_width=True)


def page_knowledge():
    ss = st.session_state
    page_header("Knowledge Base and Rule Explorer", "Inspect the facts, thresholds and rules behind every conclusion.")
    out = require_output()
    kb, rules = out.kb, out.rules
    tabs = st.tabs(["Facts", "Knowledge base", "Rules", "Rules fired", "Conflict strategy & limits"])

    with tabs[0]:
        st.caption("Input facts come from your table. Derived facts were produced by the rules.")
        rows = []
        for r in out.results:
            rows += [{"Subject": r.name, "Fact": str(f), "Type": "input"} for f in r.input_facts]
            rows += [{"Subject": r.name, "Fact": str(f), "Type": "derived"} for f in r.derived_facts]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.markdown("**Final conclusions:** " + ", ".join(
            f"`priority({r.name}, {r.final_priority})`" for r in out.results))

    with tabs[1]:
        st.dataframe(pd.DataFrame([{"Threshold": k, "Value": v, "Meaning": THRESHOLD_DESCRIPTIONS[k]}
                                   for k, v in kb.thresholds.items()]), hide_index=True, use_container_width=True)
        with st.expander("Change thresholds"):
            with st.form("threshold_form"):
                t = ss.thresholds
                a, b, c = st.columns(3)
                low_m = a.number_input("low_marks", 0.0, 100.0, float(t["low_marks"]), 1.0)
                med_m = b.number_input("medium_marks", 0.0, 100.0, float(t["medium_marks"]), 1.0)
                good_m = c.number_input("good_marks", 0.0, 100.0, float(t["good_marks"]), 1.0)
                d, e, f = st.columns(3)
                crit = d.number_input("critical_days", 0, 365, int(t["critical_days"]), 1)
                urg = e.number_input("urgent_days", 0, 365, int(t["urgent_days"]), 1)
                soon = f.number_input("soon_days", 0, 365, int(t["soon_days"]), 1)
                g, h = st.columns(2)
                conf = g.number_input("low_confidence", 1, 5, int(t["low_confidence"]), 1)
                default = h.selectbox("default_priority", ["low", "medium", "high"],
                                      index=["low", "medium", "high"].index(t["default_priority"]))
                apply_clicked = st.form_submit_button("Apply thresholds")
            if apply_clicked:
                candidate = {"low_marks": low_m, "medium_marks": med_m, "good_marks": good_m,
                             "critical_days": crit, "urgent_days": urg, "soon_days": soon,
                             "low_confidence": conf, "default_priority": default}
                try:
                    KnowledgeBase(candidate)
                    ss.thresholds = candidate
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            if st.button("Reset to defaults"):
                ss.thresholds = dict(DEFAULT_THRESHOLDS)
                st.rerun()

    with tabs[2]:
        fired_by = {rule.id: [r.name for r in out.results if rule.id in r.fired_rule_ids] for rule in rules}
        table = pd.DataFrame([{"ID": r.id, "Stage": r.stage, "Name": r.name, "IF": r.if_text(kb),
                               "THEN": r.then_text(kb), "Explanation": r.explanation,
                               "Fired for": ", ".join(fired_by[r.id]) or "-"} for r in rules])
        st.dataframe(table, hide_index=True, use_container_width=True)
        st.caption("Stages run in this order: " + " -> ".join(STAGES) + ". Rules are defined in rules.py.")

    with tabs[3]:
        matrix = pd.DataFrame({r.name: ["Yes" if rule.id in r.fired_rule_ids else "-" for rule in rules]
                               for r in out.results}, index=[rule.id for rule in rules])
        st.dataframe(matrix, use_container_width=True)

    with tabs[4]:
        st.markdown("**Conflict-resolution strategy**")
        st.write(CONFLICT_STRATEGY_TEXT)
        st.markdown("**Limitations of this simplified model**")
        for item in LIMITATIONS:
            st.markdown(f"- {item}")


def page_trace():
    page_header("Reasoning Trace and Explainable AI",
                "Every line below is recorded while the rules are evaluated. Nothing is written by hand.")
    out = require_output()
    names = [r.name for r in out.results]
    name = st.selectbox("Subject", names)
    result = out.result_for(name)
    st.markdown(f'<div class="ssa-card">{badge(result.final_priority)}<p style="margin:.6rem 0 0 0">'
                f'{esc(result.explanation)}</p></div>', unsafe_allow_html=True)

    forward, backward = st.tabs(["Forward chaining trace", "Backward chaining: ask 'why?'"])
    with forward:
        for step in explanation.trace_steps(result):
            with st.expander(step["title"], expanded=step["title"].startswith(("Step 5", "Step 7"))):
                st.code("\n".join(step["lines"]) or "(nothing to show)", language="text")
        st.download_button("Download this trace (.txt)", explanation.trace_to_text(result),
                           file_name=f"trace_{name.replace(' ', '_')}.txt")
    with backward:
        st.caption("Backward chaining starts from a GOAL and searches for the rules and facts that could prove it. "
                   "Forward chaining (the other tab) starts from facts and derives everything it can.")
        level = st.radio("Goal: is the subject at this priority?", ["high", "medium", "low"], horizontal=True,
                         format_func=lambda x: x.capitalize())
        subject = result.subject
        node = BackwardChainer(out.kb, out.rules).prove_priority(subject, level)
        if node.proven:
            st.success(f"Why is {name} a {level}-priority subject? The goal can be PROVEN, as shown below.")
        else:
            st.warning(f"The goal priority({name}, {level}) cannot be proven. The forward engine concluded "
                       f"{result.final_priority}.")
        st.code(explanation.proof_to_text(node), language="text")


def page_reports():
    page_header("Reports and Export", "Downloads are generated from the same results you see on screen.")
    out = require_output()
    who = (out.student_name or "student").replace(" ", "_")
    c1, c2, c3 = st.columns(3)
    c1.download_button("Study plan (CSV)", plan_to_csv(out), file_name=f"study_plan_{who}.csv",
                       mime="text/csv", use_container_width=True)
    c2.download_button("Inputs and reasoning (JSON)", build_json_text(out), file_name=f"study_reasoning_{who}.json",
                       mime="application/json", use_container_width=True)
    c3.download_button("Printable summary (HTML)", build_html_summary(out), file_name=f"study_summary_{who}.html",
                       mime="text/html", use_container_width=True)
    st.caption("Open the HTML summary in a browser and press Ctrl+P to print it or save it as a PDF.")
    with st.expander("Preview: text summary", expanded=True):
        st.code(build_text_summary(out), language="text")
    with st.expander("Preview: study plan table"):
        st.dataframe(plan_dataframe(out), hide_index=True, use_container_width=True)


def sidebar_navigation() -> str:
    with st.sidebar:
        st.markdown('<div class="ssa-brand"><div class="ssa-logo">S</div><div><div class="ssa-brand-name">'
                    'Smart Study Advisor</div><div class="ssa-brand-sub">Rule-based KRR system</div></div></div>',
                    unsafe_allow_html=True)
        page = st.radio("Navigate", PAGES, key="page", label_visibility="collapsed")
        st.divider()
        st.caption("Facts + IF-THEN rules + an inference engine. No machine learning.")
    return page


def footer() -> None:
    st.markdown('<div class="ssa-footer">Smart Study Advisor &middot; KRR semester project &middot; '
                'Advisory recommendations only.</div>', unsafe_allow_html=True)


def main() -> None:
    init_state()
    page = sidebar_navigation()
    ss = st.session_state
    # When the user comes back to the inputs page, restart the table from the latest edits.
    if page == "Student Inputs" and ss.last_page != "Student Inputs":
        ss.base_df = ss.edited_df.copy()
        ss.editor_version += 1
    ss.last_page = page
    {"Dashboard": page_dashboard, "Student Inputs": page_inputs, "Recommendations": page_recommendations,
     "Study Planner": page_planner, "Knowledge Base & Rules": page_knowledge, "Reasoning Trace": page_trace,
     "Reports": page_reports}[page]()
    footer()


main()
