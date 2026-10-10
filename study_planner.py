"""
study_planner.py - STUDY-TIME ALLOCATION
=========================================
Turns inferred priorities into minutes of study.

Method (deterministic and explainable):
  1. Convert the daily hours to minutes and cut them into blocks (default 15 minutes).
  2. Each subject gets a weight from its priority (High 3, Medium 2, Low 1 by default).
  3. Ideal share = weight / total weight * number of blocks.
  4. Give every subject the whole blocks of its share, then hand the leftover blocks to the subjects
     with the largest fractional parts (the "largest remainder" method). Ties go to the heavier weight,
     then to the name in alphabetical order.
Because blocks are whole numbers, the total can never exceed the daily limit and nobody gets a negative time.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from knowledge_base import (DEFAULT_WEIGHTS, MAX_DAILY_HOURS, MIN_DAILY_HOURS, PRIORITY_LEVELS,
                            PRIORITY_RANK, validate_daily_hours)

MIN_MEANINGFUL_MINUTES = 30      # shorter sessions are flagged as "too short to be useful"
EXAM_DAY_FACTOR = 0.5            # on the exam day itself a subject gets a lighter revision slot
MAX_TIMETABLE_DAYS = 14


@dataclass(frozen=True)
class PlanItem:
    name: str
    priority: str
    days_left: int = 365


@dataclass
class Allocation:
    name: str
    priority: str
    weight: float
    minutes: int
    share_percent: float
    days_left: int = 365


@dataclass
class AllocationSummary:
    available_minutes: int
    allocated_minutes: int
    unallocated_minutes: int
    block_minutes: int
    balanced: bool                     # True when nothing is left over
    notes: list[str] = field(default_factory=list)


@dataclass
class DayPlan:
    day_offset: int
    day_date: date
    label: str
    allocations: list[Allocation]
    exam_subjects: list[str]
    summary: AllocationSummary


def items_from_results(results) -> list[PlanItem]:
    return [PlanItem(r.name, r.final_priority, r.subject.days_left) for r in results]


def _check_weights(weights: Optional[dict]) -> dict:
    merged = {**DEFAULT_WEIGHTS, **(weights or {})}
    for level in PRIORITY_LEVELS:
        value = merged.get(level)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or math.isnan(value) or value < 0:
            raise ValueError(f"Weight for '{level}' must be a number >= 0.")
    return merged


def _largest_remainder(weights: dict[str, float], total_blocks: int) -> dict[str, int]:
    """Split total_blocks among names in proportion to weights (whole numbers only)."""
    total_weight = sum(weights.values())
    if total_weight <= 0 or total_blocks <= 0:
        return {name: 0 for name in weights}
    quotas = {n: w / total_weight * total_blocks for n, w in weights.items()}
    blocks = {n: int(math.floor(q + 1e-9)) for n, q in quotas.items()}
    leftover = total_blocks - sum(blocks.values())
    order = sorted(weights, key=lambda n: (-round(quotas[n] - blocks[n], 9), -weights[n], n.casefold()))
    for name in order[:max(leftover, 0)]:
        blocks[name] += 1
    return blocks


def _allocate(items, daily_hours, weights, block_minutes, factors=None):
    hours, errors = validate_daily_hours(daily_hours)
    if errors:
        raise ValueError(errors[0])
    if block_minutes not in (5, 10, 15, 20, 30, 60):
        raise ValueError("Block size must be 5, 10, 15, 20, 30 or 60 minutes.")
    names = [i.name for i in items]
    if len(names) != len(set(names)):
        raise ValueError("Subject names must be unique.")
    weight_table = _check_weights(weights)
    for item in items:
        if item.priority not in PRIORITY_RANK:
            raise ValueError(f"Unknown priority '{item.priority}' for {item.name}.")

    available = int(round(hours * 60))
    total_blocks = available // block_minutes
    notes: list[str] = []

    if not items:
        summary = AllocationSummary(available, 0, available, block_minutes, False,
                                    ["No subjects to plan. Add subjects first."])
        return [], summary

    factors = factors or {}
    weights_by_name = {i.name: weight_table[i.priority] * factors.get(i.name, 1.0) for i in items}
    blocks = _largest_remainder(weights_by_name, total_blocks)
    total_weight = sum(weights_by_name.values())
    if total_weight <= 0:
        notes.append("All weights are zero, so no time could be allocated. Increase a weight.")

    allocations = []
    for item in items:
        minutes = blocks[item.name] * block_minutes
        share = (weights_by_name[item.name] / total_weight * 100) if total_weight > 0 else 0.0
        allocations.append(Allocation(item.name, item.priority, weights_by_name[item.name],
                                      minutes, round(share, 1), item.days_left))
    allocations.sort(key=lambda a: (-PRIORITY_RANK[a.priority], -a.minutes, a.name.casefold()))

    allocated = sum(a.minutes for a in allocations)
    unallocated = available - allocated
    if total_blocks < len(items) and total_weight > 0:
        zero = [a.name for a in allocations if a.minutes == 0]
        notes.append(f"Only {available} minutes are available for {len(items)} subjects. "
                     f"{len(zero)} subject(s) get no time today ({', '.join(zero)}). "
                     "Increase the daily hours or reduce the number of subjects.")
    short = [a.name for a in allocations if 0 < a.minutes < MIN_MEANINGFUL_MINUTES]
    if short:
        notes.append(f"Sessions shorter than {MIN_MEANINGFUL_MINUTES} minutes are probably too short to be "
                     f"effective: {', '.join(short)}.")
    if unallocated > 0 and total_weight > 0:
        notes.append(f"Rounding: {unallocated} minute(s) of your {available} could not be split into "
                     f"{block_minutes}-minute blocks and are left free (rest or buffer time).")
    return allocations, AllocationSummary(available, allocated, unallocated, block_minutes,
                                          unallocated == 0 and allocated > 0, notes)


def allocate_daily(items: list[PlanItem], daily_hours, weights: Optional[dict] = None,
                   block_minutes: int = 15):
    """Public function: returns (allocations, summary). Raises ValueError on invalid input."""
    return _allocate(items, daily_hours, weights, block_minutes)


def build_timetable(items: list[PlanItem], daily_hours, weights: Optional[dict] = None,
                    block_minutes: int = 15, start_date: Optional[date] = None,
                    max_days: int = MAX_TIMETABLE_DAYS) -> list[DayPlan]:
    """Multi-day timetable. A subject is studied on day d only while d <= days_left.
    On its exam day a subject gets a lighter slot (EXAM_DAY_FACTOR). An exam today (0 days) appears only on day 0."""
    if not items:
        _allocate([], daily_hours, weights, block_minutes)      # still validates the hours
        return []
    start = start_date or date.today()
    horizon = max(1, min(max_days, max(i.days_left for i in items) + 1))
    plans = []
    for offset in range(horizon):
        todays = [i for i in items if i.days_left >= offset]
        exams = [i.name for i in todays if i.days_left == offset]
        factors = {name: EXAM_DAY_FACTOR for name in exams}
        allocations, summary = _allocate(todays, daily_hours, weights, block_minutes, factors)
        when = start + timedelta(days=offset)
        label = ("Today" if offset == 0 else f"Day {offset}") + f" - {when.strftime('%a %d %b')}"
        plans.append(DayPlan(offset, when, label, allocations, exams, summary))
    return plans


def minutes_text(minutes: int) -> str:
    """90 -> '1 h 30 min'."""
    hours, mins = divmod(int(minutes), 60)
    if hours and mins:
        return f"{hours} h {mins} min"
    if hours:
        return f"{hours} h"
    return f"{mins} min"
