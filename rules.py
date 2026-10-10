"""
rules.py - THE RULE BASE
========================
Every rule is DATA (a Rule object), not an if-statement hidden in the UI.
A rule says:  IF <conditions> THEN <conclusion>.

Rules run in four STAGES (the engine runs them in this order):
  urgency  - U1..U4 : classify how close the exam is
  base     - R1..R4, R6 : propose a base priority
  default  - R7 : fires only if no base rule fired
  adjust   - R5, R8 : raise the priority by one level

HOW TO CHANGE A RULE SAFELY
  1. Prefer changing a threshold (knowledge_base.DEFAULT_THRESHOLDS) over editing a rule.
  2. Keep IDs unique; keep 'stage' one of STAGES.
  3. Use "@name" to point to a threshold.
  4. Run:  python -m unittest discover tests
"""
from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Any

STAGES = ("urgency", "base", "default", "adjust")

OPERATORS = {
    "<": operator.lt, "<=": operator.le,
    ">": operator.gt, ">=": operator.ge,
    "==": operator.eq, "!=": operator.ne,
}
# "absent" is a special operator: true when NO fact with that predicate exists
# (negation as failure - used by the default rule R7).


@dataclass(frozen=True)
class Condition:
    """One test inside the IF part, e.g. marks < @low_marks."""
    predicate: str
    op: str
    value: Any = None

    def text(self, kb=None) -> str:
        """Readable form, e.g. 'marks < low_marks (50)'."""
        if self.op == "absent":
            return f"no {self.predicate} fact exists yet"
        value = self.value
        if isinstance(value, str) and value.startswith("@"):
            name = value[1:]
            shown = f"{name} ({kb.resolve(value)})" if kb is not None else name
        else:
            shown = str(value)
        return f"{self.predicate} {self.op} {shown}"


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    stage: str
    conditions: tuple
    conclusion_predicate: str
    conclusion_value: Any
    explanation: str
    salience: int = 0          # tie-breaker inside conflict resolution (higher wins)

    def if_text(self, kb=None) -> str:
        return " AND ".join(c.text(kb) for c in self.conditions)

    def then_text(self, kb=None) -> str:
        value = self.conclusion_value
        if kb is not None:
            value = kb.resolve(value)
        elif isinstance(value, str) and value.startswith("@"):
            value = value[1:]
        return f"{self.conclusion_predicate} = {value}"


def build_rules() -> list[Rule]:
    """Return the full rule base."""
    C = Condition
    return [
        # ---------------- urgency classification ----------------
        Rule("U1", "Exam is critical", "urgency",
             (C("days_left", "<=", "@critical_days"),),
             "urgency", "critical",
             "The exam is today or tomorrow, so the situation is critical."),
        Rule("U2", "Exam is urgent", "urgency",
             (C("days_left", ">", "@critical_days"), C("days_left", "<=", "@urgent_days")),
             "urgency", "urgent",
             "The exam is only a few days away."),
        Rule("U3", "Exam is soon", "urgency",
             (C("days_left", ">", "@urgent_days"), C("days_left", "<=", "@soon_days")),
             "urgency", "soon",
             "The exam is within about a week."),
        Rule("U4", "Exam is comfortably far", "urgency",
             (C("days_left", ">", "@soon_days"),),
             "urgency", "comfortable",
             "The exam is more than a week away."),

        # ---------------- base priority ----------------
        Rule("R1", "Low marks + approaching exam", "base",
             (C("marks", "<", "@low_marks"), C("days_left", "<=", "@soon_days")),
             "base_candidate", "high",
             "Marks are low and the exam is close, so this subject is high priority.", salience=100),
        Rule("R2", "Extremely urgent exam", "base",
             (C("days_left", "<=", "@urgent_days"),),
             "base_candidate", "high",
             "The exam is extremely close, so this subject is high priority.", salience=90),
        Rule("R3", "Low academic performance", "base",
             (C("marks", "<", "@low_marks"),),
             "base_candidate", "high",
             "Marks are below the pass-safe level, so this subject needs strong attention.", salience=80),
        Rule("R4", "Moderate academic performance", "base",
             (C("marks", ">=", "@low_marks"), C("marks", "<", "@medium_marks")),
             "base_candidate", "medium",
             "Marks are average, so this subject deserves moderate attention.", salience=60),
        Rule("R6", "Strong marks, easy subject, distant exam", "base",
             (C("marks", ">=", "@good_marks"), C("days_left", ">", "@soon_days"),
              C("difficulty", "==", "low")),
             "base_candidate", "low",
             "Marks are high, the subject is easy and the exam is far away, so priority is low.", salience=40),

        # ---------------- default ----------------
        Rule("R7", "Default priority", "default",
             (C("base_candidate", "absent"),),
             "base_candidate", "@default_priority",
             "No stronger rule matched, so the default priority is used.", salience=0),

        # ---------------- adjustments (one level up, at most once) ----------------
        Rule("R5", "Hard subject raises priority", "adjust",
             (C("difficulty", "==", "high"), C("base_priority", "!=", "high")),
             "boost", 1,
             "The subject is hard, so its priority is raised by one level.", salience=50),
        Rule("R8", "Shaky confidence raises priority", "adjust",
             (C("confidence", "<=", "@low_confidence"), C("base_priority", "!=", "high")),
             "boost", 1,
             "The student feels unsure about this subject, so its priority is raised by one level.",
             salience=40),
    ]


def natural_key(rule_id: str):
    """Sort 'R10' after 'R2'."""
    letters = "".join(ch for ch in rule_id if ch.isalpha())
    digits = "".join(ch for ch in rule_id if ch.isdigit())
    return (letters, int(digits) if digits else 0)


CONFLICT_STRATEGY_TEXT = (
    "When several base rules propose different priorities, the engine keeps ALL of them in the trace, "
    "then picks ONE winner with this fixed order: (1) the most severe level wins "
    "(high > medium > low); (2) if levels tie, the rule with the higher salience wins; "
    "(3) if salience ties, the smaller rule ID wins. Adjustment rules (R5, R8) raise the winner by "
    "at most ONE level in total and never go above High. The result does not depend on the order in "
    "which rules are stored."
)

LIMITATIONS = [
    "Thresholds are simple cut-offs, so 49.9% and 50% are treated very differently.",
    "The model uses only marks, days left, difficulty and confidence; it does not know topic weights or exam format.",
    "Rules do not learn from the student's results; an expert must update them by hand.",
    "Study-time weights (3/2/1) are a design choice, not scientifically optimal values.",
    "The advice is advisory; real study plans also depend on sleep, health and personal habits.",
]
