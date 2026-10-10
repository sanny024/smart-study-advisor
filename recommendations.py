"""
recommendations.py - RECOMMENDATION GENERATION
===============================================
Combines the reasoning results (priority, urgency, reasons) with the planner output (minutes)
and the advice texts stored in the knowledge base. No new decisions are made here;
this module only formats the conclusions of the inference engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import knowledge_base as kbmod
from knowledge_base import PRIORITY_RANK
from study_planner import minutes_text


@dataclass
class Recommendation:
    subject: str
    priority: str
    urgency: str
    days_left: int
    marks: float
    difficulty: str
    daily_minutes: int
    urgency_warning: str
    strategy: str
    revision_steps: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def daily_time_text(self) -> str:
        return minutes_text(self.daily_minutes)


def _warning(urgency: str, days: int) -> str:
    template = kbmod.URGENCY_WARNINGS.get(urgency, "")
    when = "TODAY" if days == 0 else "TOMORROW" if days == 1 else f"in {days} days"
    return template.format(when=when, days=days)


def build_recommendations(results, allocations, kb) -> list[Recommendation]:
    minutes_by_name = {a.name: a.minutes for a in allocations}
    recs = []
    for r in results:
        s = r.subject
        band = kb.performance_band(s.marks)
        steps = [kbmod.PERFORMANCE_ADVICE[band], kbmod.URGENCY_ADVICE.get(r.urgency, "")]
        if r.final_priority == "high":
            steps.append("Revise this subject first in every study session.")
        if r.boost_rule_ids and "R8" in r.boost_rule_ids:
            steps.append("You rated your confidence low: finish a short self-test to find the exact weak topics.")
        recs.append(Recommendation(
            subject=s.name, priority=r.final_priority, urgency=r.urgency, days_left=s.days_left,
            marks=s.marks, difficulty=s.difficulty, daily_minutes=minutes_by_name.get(s.name, 0),
            urgency_warning=_warning(r.urgency, s.days_left),
            strategy=kbmod.DIFFICULTY_STRATEGIES[s.difficulty],
            revision_steps=[x for x in steps if x], reasons=list(r.reasons)))
    recs.sort(key=lambda x: (-PRIORITY_RANK[x.priority], x.days_left, x.marks, x.subject.casefold()))
    return recs


def next_action(recs: list[Recommendation]) -> str:
    """The single most useful thing to do now (recs are already sorted)."""
    if not recs:
        return "Add your subjects on the 'Student Inputs' page to get a recommendation."
    top = recs[0]
    when = {0: "today", 1: "tomorrow"}.get(top.days_left, f"in {top.days_left} days")
    return (f"Start with {top.subject} ({top.priority.capitalize()} priority, exam {when}). "
            f"Plan about {top.daily_time_text} for it today.")
