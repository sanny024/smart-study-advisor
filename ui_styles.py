"""
ui_styles.py - LOOK AND FEEL
============================
Custom CSS kept in one place. We style our OWN classes (ssa-*) and only a few stable Streamlit
test-ids, so small Streamlit updates are unlikely to break the design. Colours keep strong
contrast for accessibility.
"""
INDIGO = "#4338CA"
DEEP = "#1E1B4B"
LAVENDER = "#F5F3FF"
LAVENDER_DARK = "#DDD6FE"
TEAL = "#0D9488"
MUTED = "#5B5B7B"

PRIORITY_COLORS = {"high": "#DC2626", "medium": "#D97706", "low": TEAL}
PRIORITY_BG = {"high": "#FEE2E2", "medium": "#FEF3C7", "low": "#CCFBF1"}
PRIORITY_FG = {"high": "#991B1B", "medium": "#92400E", "low": "#115E59"}

CSS = f"""
<style>
.block-container {{ padding-top: 2rem; padding-bottom: 3rem; max-width: 1200px; }}
html, body, [class*="css"] {{ font-family: "Segoe UI", "Inter", system-ui, -apple-system, Arial, sans-serif; }}
h1, h2, h3 {{ color: {DEEP}; letter-spacing: -0.01em; }}
[data-testid="stSidebar"] {{ background: {LAVENDER}; border-right: 1px solid {LAVENDER_DARK}; }}

.ssa-brand {{ display:flex; align-items:center; gap:.7rem; margin:.2rem 0 1rem 0; }}
.ssa-logo {{ width:42px; height:42px; border-radius:12px; background:{INDIGO}; color:#fff; display:flex;
            align-items:center; justify-content:center; font-weight:700; font-size:1.1rem; }}
.ssa-brand-name {{ font-weight:700; color:{DEEP}; line-height:1.1; }}
.ssa-brand-sub {{ font-size:.75rem; color:{MUTED}; }}

.ssa-hero {{ background:linear-gradient(135deg,{INDIGO} 0%,#6D5DD3 100%); color:#fff; border-radius:18px;
            padding:1.6rem 1.8rem; box-shadow:0 8px 24px rgba(67,56,202,.25); margin-bottom:1.2rem; }}
.ssa-hero h1 {{ color:#fff; margin:0 0 .3rem 0; font-size:1.8rem; }}
.ssa-hero p {{ margin:0; color:#EDE9FE; max-width:760px; }}
.ssa-page-title {{ margin-bottom:.2rem; }}
.ssa-page-sub {{ color:{MUTED}; margin-bottom:1.1rem; }}

.ssa-card {{ background:#fff; border:1px solid {LAVENDER_DARK}; border-radius:16px; padding:1.1rem 1.25rem;
            box-shadow:0 2px 10px rgba(30,27,75,.06); margin-bottom:1rem; }}
.ssa-kpi {{ background:#fff; border:1px solid {LAVENDER_DARK}; border-radius:16px; padding:1rem 1.2rem;
           box-shadow:0 2px 10px rgba(30,27,75,.06); border-top:4px solid {INDIGO}; }}
.ssa-kpi .label {{ color:{MUTED}; font-size:.8rem; text-transform:uppercase; letter-spacing:.05em; }}
.ssa-kpi .value {{ color:{DEEP}; font-size:1.9rem; font-weight:700; line-height:1.2; }}
.ssa-kpi .hint {{ color:{MUTED}; font-size:.78rem; }}
.ssa-kpi.teal {{ border-top-color:{TEAL}; }}

.ssa-badge {{ display:inline-block; padding:.15rem .65rem; border-radius:999px; font-size:.78rem; font-weight:600; }}
.ssa-action {{ background:{LAVENDER}; border-left:5px solid {TEAL}; border-radius:12px; padding:1rem 1.2rem; color:{DEEP}; }}
.ssa-action b {{ color:{INDIGO}; }}
.ssa-rec-title {{ font-size:1.1rem; font-weight:700; color:{DEEP}; margin-bottom:.3rem; }}
.ssa-meta {{ color:{MUTED}; font-size:.85rem; }}
.ssa-note {{ color:{MUTED}; font-size:.85rem; }}
.ssa-footer {{ margin-top:2.5rem; padding-top:1rem; border-top:1px solid {LAVENDER_DARK}; color:{MUTED};
              font-size:.8rem; text-align:center; }}
.ssa-empty {{ text-align:center; padding:2.2rem 1rem; border:2px dashed {LAVENDER_DARK}; border-radius:16px;
             color:{MUTED}; background:{LAVENDER}; }}
@media (max-width: 640px) {{
  .ssa-hero {{ padding:1.1rem; }} .ssa-hero h1 {{ font-size:1.4rem; }} .ssa-kpi .value {{ font-size:1.5rem; }}
}}
</style>
"""
