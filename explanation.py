"""
explanation.py - THE EXPLANATION FACILITY (explainable AI)
===========================================================
Turns the real results of the inference engine into readable text.
Nothing here is invented: every line is read from the evaluations the engine recorded.
This module deliberately imports nothing from the engine (it works with the result objects it is given).
"""
from __future__ import annotations

STAGE_TITLES = {
    "urgency": "Step 2 - Urgency classification (rules U1-U4)",
    "base": "Step 3 - Base priority rules (R1-R4, R6)",
    "default": "Step 4 - Default rule (R7, only if nothing else fired)",
    "adjust": "Step 6 - Adjustment rules (R5, R8: raise priority one level)",
}


def _evaluation_lines(evaluation) -> list[str]:
    mark = "[MATCHED]    " if evaluation.matched else "[not matched]"
    lines = [f"{mark} {evaluation.rule_id} - {evaluation.rule_name}",
             f"    IF   {evaluation.if_text}",
             f"    THEN {evaluation.then_text}"]
    for cond in evaluation.conditions:
        verdict = "true" if cond.passed else "false"
        lines.append(f"      - {cond.text}   (actual: {cond.actual}) -> {verdict}")
    return lines


def summarize(result) -> str:
    """One paragraph that explains the final priority."""
    name = result.name
    final = result.final_priority.capitalize()
    base = result.base_priority.capitalize()
    base_rules = [c["rule_id"] for c in result.candidates]
    text = f"{name} receives {final} priority. "
    if len(base_rules) > 1:
        text += (f"The base priority {base} comes from rules {', '.join(base_rules)} "
                 f"(winner: {result.winning_rule_id}). ")
    elif base_rules:
        text += f"The base priority {base} comes from rule {base_rules[0]}. "
    else:
        text += f"The base priority {base} comes from the knowledge-base default. "
    if result.boost_rule_ids:
        text += (f"Then {', '.join(result.boost_rule_ids)} raised it one level to {final}. ")
    text += f"Exam urgency: {result.urgency}."
    return text


def trace_steps(result) -> list[dict]:
    """Return the reasoning trace as a list of {'title': str, 'lines': [str]}."""
    steps = [{"title": "Step 1 - Input facts",
              "lines": [str(f) for f in result.input_facts]}]
    for stage in ("urgency", "base", "default"):
        lines = []
        for ev in [e for e in result.evaluations if e.stage == stage]:
            lines.extend(_evaluation_lines(ev))
        steps.append({"title": STAGE_TITLES[stage], "lines": lines})

    candidates = ", ".join(f"{c['rule_id']}->{c['level']}" for c in result.candidates) or "none"
    steps.append({"title": "Step 5 - Conflict resolution (intermediate conclusion)",
                  "lines": [f"Base candidates that fired: {candidates}",
                            result.conflict_note,
                            f"Intermediate conclusion: base_priority({result.name}, {result.base_priority})"]})

    adjust_lines = []
    for ev in [e for e in result.evaluations if e.stage == "adjust"]:
        adjust_lines.extend(_evaluation_lines(ev))
    steps.append({"title": STAGE_TITLES["adjust"], "lines": adjust_lines})

    steps.append({"title": "Step 7 - Final priority and explanation",
                  "lines": [f"Final: priority({result.name}, {result.final_priority})",
                            f"Rules that fired: {', '.join(result.fired_rule_ids)}",
                            "",
                            "Reasons:"] + [f"  * {r}" for r in result.reasons] + ["", result.explanation]})
    return steps


def trace_to_text(result) -> str:
    out = []
    for step in trace_steps(result):
        out.append(step["title"])
        out.append("-" * len(step["title"]))
        out.extend(step["lines"])
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def proof_to_text(node, indent: int = 0) -> str:
    """Render a backward-chaining proof tree as indented text."""
    mark = "[PROVEN]" if node.proven else "[FAILED]"
    pad = "    " * indent
    line = f"{pad}{mark} {node.goal}"
    if node.note:
        line += f"  <- {node.note}"
    lines = [line]
    for child in node.children:
        lines.append(proof_to_text(child, indent + 1))
    return "\n".join(lines)
