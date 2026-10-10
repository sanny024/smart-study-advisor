"""
advisor.py - THE PIPELINE
=========================
One function runs everything in order, so the UI, the exports and the tests all use the SAME results:
    subjects -> facts -> inference (rules) -> planner -> recommendations
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from inference_engine import InferenceEngine, SubjectResult
from knowledge_base import KnowledgeBase, Subject, validate_daily_hours
from recommendations import Recommendation, build_recommendations
from rules import Rule, build_rules
from study_planner import (Allocation, AllocationSummary, DayPlan, allocate_daily, build_timetable,
                           items_from_results)


@dataclass
class AdvisorOutput:
    student_name: str
    daily_hours: float
    kb: KnowledgeBase
    rules: list[Rule]
    subjects: list[Subject]
    results: list[SubjectResult]
    allocations: list[Allocation]
    summary: AllocationSummary
    timetable: list[DayPlan]
    recommendations: list[Recommendation]
    block_minutes: int = 15
    weights: dict = field(default_factory=dict)

    def result_for(self, name: str) -> SubjectResult:
        for r in self.results:
            if r.name == name:
                return r
        raise KeyError(name)


def run_advisor(student_name: str, subjects: list[Subject], daily_hours,
                kb: Optional[KnowledgeBase] = None, rules: Optional[list[Rule]] = None,
                block_minutes: int = 15, start_date: Optional[date] = None) -> AdvisorOutput:
    kb = kb or KnowledgeBase()
    rules = rules if rules is not None else build_rules()
    hours, errors = validate_daily_hours(daily_hours)
    if errors:
        raise ValueError(errors[0])
    engine = InferenceEngine(kb, rules)
    results = engine.infer_all(subjects)
    items = items_from_results(results)
    allocations, summary = allocate_daily(items, hours, kb.weights, block_minutes)
    timetable = build_timetable(items, hours, kb.weights, block_minutes, start_date)
    recs = build_recommendations(results, allocations, kb)
    return AdvisorOutput((student_name or "").strip(), hours, kb, rules, subjects, results, allocations,
                         summary, timetable, recs, block_minutes, dict(kb.weights))
