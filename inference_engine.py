"""
inference_engine.py - FORWARD CHAINING, CONFLICT RESOLUTION, BACKWARD CHAINING
================================================================================
FORWARD CHAINING (data-driven): start from the known facts, fire every rule whose
conditions are true, add the new conclusions to working memory, repeat until nothing
new can be derived. Rules are grouped in stages (see rules.py); each stage is run to a
fixed point before the next one starts.

CONFLICT RESOLUTION: several base rules may fire with different conclusions
(e.g. R2 says High, R4 says Medium). resolve_conflict() chooses ONE winner
deterministically, and the trace keeps every rule that fired.

BACKWARD CHAINING (goal-driven): start from a goal such as priority(AI, high) and work
backwards: which rules could conclude this, and are their conditions supported by facts
(or by sub-goals that can be proven)? See BackwardChainer at the bottom.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Optional

import explanation
from knowledge_base import PRIORITY_LEVELS, PRIORITY_RANK, Fact, KnowledgeBase, Subject
from rules import OPERATORS, STAGES, Condition, Rule, build_rules, natural_key


# --------------------------------------------------------------------------
# Working memory
# --------------------------------------------------------------------------
class WorkingMemory:
    """The set of facts currently believed true (input facts + derived facts)."""

    def __init__(self, facts=()):
        self._facts: list[Fact] = []
        for fact in facts:
            self.add(fact)

    def add(self, fact: Fact) -> bool:
        """Add a fact. Returns False if it was already known."""
        if fact in self._facts:
            return False
        self._facts.append(fact)
        return True

    def values(self, predicate: str, subject: str) -> list:
        return [f.value for f in self._facts if f.predicate == predicate and f.subject == subject]

    def all(self) -> list[Fact]:
        return list(self._facts)


# --------------------------------------------------------------------------
# Result objects (what the UI, exports and tests read)
# --------------------------------------------------------------------------
@dataclass
class ConditionResult:
    text: str          # e.g. "marks < low_marks (50)"
    actual: Any        # the value found in working memory, or "unknown"
    passed: bool


@dataclass
class RuleEvaluation:
    rule_id: str
    rule_name: str
    stage: str
    matched: bool
    conditions: list[ConditionResult]
    if_text: str
    then_text: str
    explanation: str


@dataclass
class SubjectResult:
    subject: Subject
    input_facts: list[Fact]
    derived_facts: list[Fact]
    evaluations: list[RuleEvaluation]
    fired_rule_ids: list[str]
    urgency: str
    candidates: list[dict]            # [{"rule_id": "R2", "level": "high"}, ...] all base rules that fired
    winning_rule_id: str
    base_priority: str
    boost_rule_ids: list[str]
    final_priority: str
    conflict_note: str
    reasons: list[str]
    explanation: str

    @property
    def name(self) -> str:
        return self.subject.name

    def to_dict(self) -> dict:
        return {
            "subject": self.name,
            "input_facts": [str(f) for f in self.input_facts],
            "derived_facts": [str(f) for f in self.derived_facts],
            "fired_rules": self.fired_rule_ids,
            "urgency": self.urgency,
            "base_candidates": self.candidates,
            "winning_base_rule": self.winning_rule_id,
            "base_priority": self.base_priority,
            "boost_rules": self.boost_rule_ids,
            "final_priority": self.final_priority,
            "conflict_resolution": self.conflict_note,
            "reasons": self.reasons,
            "explanation": self.explanation,
        }


# --------------------------------------------------------------------------
# Conflict resolution
# --------------------------------------------------------------------------
def resolve_conflict(candidates: list[tuple[Rule, str]]) -> tuple[Rule, str]:
    """Pick ONE winning (rule, level) from all fired base rules.

    Order: highest level -> highest salience -> smallest rule ID.
    The sort key makes the answer independent of the order of the input list.
    """
    if not candidates:
        raise ValueError("resolve_conflict needs at least one candidate")
    return sorted(candidates,
                  key=lambda c: (-PRIORITY_RANK[c[1]], -c[0].salience, natural_key(c[0].id)))[0]


# --------------------------------------------------------------------------
# Forward-chaining engine
# --------------------------------------------------------------------------
class InferenceEngine:
    def __init__(self, kb: Optional[KnowledgeBase] = None, rules: Optional[list[Rule]] = None):
        self.kb = kb or KnowledgeBase()
        self.rules = list(rules) if rules is not None else build_rules()
        ids = [r.id for r in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("Rule IDs must be unique.")
        for rule in self.rules:
            if rule.stage not in STAGES:
                raise ValueError(f"Rule {rule.id} has unknown stage '{rule.stage}'.")

    # ---- condition / rule evaluation ----
    def _check_condition(self, cond: Condition, memory: WorkingMemory, name: str) -> ConditionResult:
        values = memory.values(cond.predicate, name)
        text = cond.text(self.kb)
        if cond.op == "absent":
            return ConditionResult(text, "none found" if not values else ", ".join(map(str, values)),
                                   not values)
        if not values:
            return ConditionResult(text, "unknown", False)
        actual = values[0]
        try:
            passed = bool(OPERATORS[cond.op](actual, self.kb.resolve(cond.value)))
        except TypeError:
            passed = False
        return ConditionResult(text, actual, passed)

    def _evaluate_rule(self, rule: Rule, memory: WorkingMemory, name: str) -> RuleEvaluation:
        results = [self._check_condition(c, memory, name) for c in rule.conditions]
        return RuleEvaluation(rule.id, rule.name, rule.stage, all(r.passed for r in results), results,
                              rule.if_text(self.kb), rule.then_text(self.kb), rule.explanation)

    def _run_stage(self, stage_rules, memory, name, evaluations, fired):
        """Fire rules of one stage until no rule can fire any more (a fixed point)."""
        pending = list(stage_rules)
        last_eval: dict[str, RuleEvaluation] = {}
        changed = True
        while changed:
            changed = False
            for rule in list(pending):
                evaluation = self._evaluate_rule(rule, memory, name)
                last_eval[rule.id] = evaluation
                if evaluation.matched:
                    fact = Fact(rule.conclusion_predicate, name, self.kb.resolve(rule.conclusion_value))
                    memory.add(fact)
                    fired.append((rule, fact))
                    pending.remove(rule)
                    changed = True
        # keep evaluations sorted by rule ID so the trace never depends on storage order
        for rule in sorted(stage_rules, key=lambda r: natural_key(r.id)):
            evaluations.append(last_eval[rule.id])

    # ---- main entry points ----
    def infer(self, subject: Subject) -> SubjectResult:
        name = subject.name
        input_facts = self.kb.facts_for(subject)
        memory = WorkingMemory(input_facts)
        evaluations: list[RuleEvaluation] = []
        fired: list[tuple[Rule, Fact]] = []

        for stage in STAGES:
            stage_rules = [r for r in self.rules if r.stage == stage]
            self._run_stage(stage_rules, memory, name, evaluations, fired)
            if stage == "default":
                self._resolve_base_priority(memory, name, fired)

        by_id = {r.id: r for r in self.rules}
        candidates = [(r, f.value) for r, f in fired if f.predicate == "base_candidate"]
        urgency_values = memory.values("urgency", name)
        urgency = urgency_values[0] if urgency_values else "unknown"
        base = memory.values("base_priority", name)[0]
        boost_ids = sorted((r.id for r, f in fired if f.predicate == "boost"), key=natural_key)

        if candidates:
            winner_rule, _ = resolve_conflict(candidates)
            winning_id = winner_rule.id
        else:
            winning_id = "(none)"
        conflict_note = self._conflict_note(candidates)

        final = base
        if boost_ids:                       # raise ONE level, never above 'high'
            final = PRIORITY_LEVELS[min(PRIORITY_LEVELS.index(base) + 1, len(PRIORITY_LEVELS) - 1)]
        derived = [f for f in memory.all() if f not in input_facts]
        fired_ids = sorted((r.id for r, _ in fired), key=lambda x: (STAGES.index(by_id[x].stage), natural_key(x)))

        reasons = [f"{rid}: {by_id[rid].explanation}" for rid in fired_ids
                   if by_id[rid].stage in ("base", "default", "adjust")]
        result = SubjectResult(
            subject=subject, input_facts=input_facts, derived_facts=derived, evaluations=evaluations,
            fired_rule_ids=fired_ids, urgency=urgency,
            candidates=[{"rule_id": r.id, "level": lvl} for r, lvl in
                        sorted(candidates, key=lambda c: natural_key(c[0].id))],
            winning_rule_id=winning_id, base_priority=base, boost_rule_ids=boost_ids,
            final_priority=final, conflict_note=conflict_note, reasons=reasons, explanation="")
        result.explanation = explanation.summarize(result)
        return result

    def infer_all(self, subjects: list[Subject]) -> list[SubjectResult]:
        return [self.infer(s) for s in subjects]

    # ---- helpers ----
    def _resolve_base_priority(self, memory, name, fired):
        """Turn the set of base_candidate facts into ONE base_priority fact."""
        candidates = [(r, f.value) for r, f in fired if f.predicate == "base_candidate"]
        if candidates:
            _, level = resolve_conflict(candidates)
        else:                               # only possible if the rule base has no default rule
            level = self.kb.thresholds["default_priority"]
        memory.add(Fact("base_priority", name, level))

    @staticmethod
    def _conflict_note(candidates) -> str:
        if not candidates:
            return "No base rule fired; the knowledge-base default priority was used."
        by_level: dict[str, list[str]] = {}
        for rule, level in sorted(candidates, key=lambda c: natural_key(c[0].id)):
            by_level.setdefault(level, []).append(rule.id)
        winner_rule, winner_level = resolve_conflict(candidates)
        if len(by_level) > 1:
            parts = "; ".join(f"{lvl.capitalize()} proposed by {', '.join(ids)}"
                              for lvl, ids in sorted(by_level.items(), key=lambda kv: -PRIORITY_RANK[kv[0]]))
            return (f"CONFLICT: {parts}. Strategy 'most severe level wins' selected "
                    f"{winner_level.capitalize()} (winning rule {winner_rule.id}).")
        ids = ", ".join(r.id for r, _ in sorted(candidates, key=lambda c: natural_key(c[0].id)))
        if len(candidates) > 1:
            return f"No conflict: {ids} all agree on {winner_level.capitalize()}."
        return f"No conflict: only {ids} proposed a base priority ({winner_level.capitalize()})."


# --------------------------------------------------------------------------
# Backward chaining
# --------------------------------------------------------------------------
@dataclass
class ProofNode:
    goal: str
    proven: bool
    rule_id: Optional[str] = None
    note: str = ""
    children: list = field(default_factory=list)


class BackwardChainer:
    """Goal-driven reasoning.

    Goal:  priority(S, L)   ("is subject S at final priority L?")
    Definition of the goal (written as two clauses):
      A) priority(S, L) :- base_priority(S, L), NOT boost(S)        (for L = high the boost is irrelevant)
      B) priority(S, L) :- base_priority(S, below(L)), boost(S)      (L = medium or high)
    Sub-goals are proven by finding the rules whose conclusion matches, and testing their
    conditions against the facts (or against further sub-goals such as base_priority).
    """
    LEAF_PREDICATES = ("marks", "days_left", "difficulty", "confidence")

    def __init__(self, kb: Optional[KnowledgeBase] = None, rules: Optional[list[Rule]] = None):
        self.kb = kb or KnowledgeBase()
        self.rules = list(rules) if rules is not None else build_rules()

    # ---- proving single conditions and rules ----
    def _prove_condition(self, cond: Condition, subject: Subject, memory: WorkingMemory) -> ProofNode:
        text = cond.text(self.kb)
        name = subject.name
        if cond.op == "absent":
            proven_ids = [r.id for r, _ in self._proven_base_rules(subject, memory)]
            ok = not proven_ids
            note = "no base rule can be proven" if ok else f"base rules {', '.join(proven_ids)} are provable"
            return ProofNode(f"{text}", ok, note=note)
        if cond.predicate in self.LEAF_PREDICATES:
            values = memory.values(cond.predicate, name)
            if not values:
                return ProofNode(text, False, note=f"no fact {cond.predicate}({name}, ?) in the knowledge base")
            actual = values[0]
            ok = bool(OPERATORS[cond.op](actual, self.kb.resolve(cond.value)))
            return ProofNode(text, ok, note=f"fact {cond.predicate}({name}, {actual}) -> {'true' if ok else 'false'}")
        if cond.predicate == "base_priority":
            level, _ = self._resolve_base(subject, memory)
            ok = bool(OPERATORS[cond.op](level, self.kb.resolve(cond.value)))
            return ProofNode(text, ok, note=f"sub-goal: base_priority({name}) resolves to {level} -> {'true' if ok else 'false'}")
        return ProofNode(text, False, note=f"unknown predicate '{cond.predicate}'")

    def _prove_rule(self, rule: Rule, subject: Subject, memory: WorkingMemory) -> ProofNode:
        children = [self._prove_condition(c, subject, memory) for c in rule.conditions]
        proven = all(c.proven for c in children)
        return ProofNode(f"{rule.id} ({rule.name}): {rule.then_text(self.kb)}", proven, rule_id=rule.id,
                         note="all conditions hold" if proven else "a condition fails", children=children)

    # ---- base priority sub-goal ----
    def _proven_base_rules(self, subject, memory):
        """Base-stage rules (not the default) whose conditions can be proven."""
        out = []
        for rule in self.rules:
            if rule.stage == "base" and self._prove_rule(rule, subject, memory).proven:
                out.append((rule, self.kb.resolve(rule.conclusion_value)))
        return out

    def _base_candidates(self, subject, memory):
        """Prove all base rules, then the default rule. Returns (proven list, node per rule id)."""
        nodes, proven = {}, []
        for rule in self.rules:
            if rule.stage == "base":
                nodes[rule.id] = self._prove_rule(rule, subject, memory)
                if nodes[rule.id].proven:
                    proven.append((rule, self.kb.resolve(rule.conclusion_value)))
        for rule in self.rules:
            if rule.stage == "default":
                nodes[rule.id] = self._prove_rule(rule, subject, memory)
                if nodes[rule.id].proven:
                    proven.append((rule, self.kb.resolve(rule.conclusion_value)))
        return proven, nodes

    def _resolve_base(self, subject, memory):
        proven, nodes = self._base_candidates(subject, memory)
        if proven:
            _, level = resolve_conflict(proven)
        else:
            level = self.kb.thresholds["default_priority"]
        return level, nodes

    def _prove_base_goal(self, subject, memory, level) -> ProofNode:
        proven, nodes = self._base_candidates(subject, memory)
        supporting = [nodes[r.id] for r in self.rules
                      if r.id in nodes and r.stage in ("base", "default")
                      and self.kb.resolve(r.conclusion_value) == level]
        higher = [r.id for r, lvl in proven if PRIORITY_RANK[lvl] > PRIORITY_RANK[level]]
        guard = ProofNode(f"no provable rule gives a base level higher than {level}", not higher,
                          note="none found" if not higher else f"rules {', '.join(higher)} prove a higher level")
        ok = any(n.proven for n in supporting) and not higher
        return ProofNode(f"base_priority({subject.name}, {level})", ok,
                         note="supported by a rule and nothing stronger" if ok else "cannot be established",
                         children=supporting + [guard])

    def _prove_boost_goal(self, subject, memory) -> ProofNode:
        nodes = [self._prove_rule(r, subject, memory) for r in self.rules if r.stage == "adjust"]
        ok = any(n.proven for n in nodes)
        return ProofNode(f"boost({subject.name})", ok,
                         note="an adjustment rule is provable" if ok else "no adjustment rule is provable",
                         children=nodes)

    # ---- the public query ----
    def prove_priority(self, subject: Subject, level: str) -> ProofNode:
        """Try to prove priority(subject, level) by working backwards."""
        if level not in PRIORITY_LEVELS:
            raise ValueError("level must be low, medium or high")
        memory = WorkingMemory(self.kb.facts_for(subject))
        root = ProofNode(f"priority({subject.name}, {level})", False)

        # Clause A: base level equals the goal and no boost applies (for 'high' a boost is irrelevant)
        base_node = self._prove_base_goal(subject, memory, level)
        if level == "high":
            clause_a = ProofNode("Clause A: base_priority is already high", base_node.proven,
                                 note="High cannot be raised further", children=[base_node])
        else:
            boost_node = self._prove_boost_goal(subject, memory)
            not_boost = ProofNode(f"NOT boost({subject.name})", not boost_node.proven,
                                  note="negation as failure", children=[boost_node])
            clause_a = ProofNode(f"Clause A: base_priority = {level} AND no boost",
                                 base_node.proven and not_boost.proven, children=[base_node, not_boost])
        root.children.append(clause_a)

        # Clause B: base level is one below the goal and a boost applies
        if level != "low":
            below = PRIORITY_LEVELS[PRIORITY_LEVELS.index(level) - 1]
            below_node = self._prove_base_goal(subject, memory, below)
            boost_node_b = self._prove_boost_goal(subject, memory)
            clause_b = ProofNode(f"Clause B: base_priority = {below} AND boost applies",
                                 below_node.proven and boost_node_b.proven,
                                 children=[below_node, boost_node_b])
            root.children.append(clause_b)

        root.proven = any(c.proven for c in root.children)
        root.note = "goal PROVEN" if root.proven else "goal CANNOT be proven"
        return root


def shuffled_rules(seed: int) -> list[Rule]:
    """Rule base in a random order (used by tests to show order does not matter)."""
    rules = build_rules()
    random.Random(seed).shuffle(rules)
    return rules
