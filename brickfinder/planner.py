"""Advisory minimum-dismantling plans with deterministic, validated fallback."""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from time import perf_counter
from typing import Literal

from ortools.sat.python import cp_model

from brickfinder.inventory import CollectionState, available_inventory, catalog_fingerprint, inventory_sources
from brickfinder.matching import Mode, by_part, matched_quantity


@dataclass(frozen=True)
class Allocation:
    part_id: str
    requested_color: int
    supplied_color: int
    quantity: int
    source_id: str  # "loose" or a physical copy UUID


@dataclass(frozen=True)
class Shortage:
    part_id: str
    requested_color: int | None
    quantity: int
    protected_quantity: int


@dataclass
class BuildPlan:
    status: Literal["optimal", "feasible", "insufficient inventory", "error"]
    minimum_proven: bool
    selected_copy_ids: list[str] = field(default_factory=list)
    allocations: list[Allocation] = field(default_factory=list)
    shortages: list[Shortage] = field(default_factory=list)
    color_substitutions: int = 0
    elapsed_seconds: float = 0.0
    inventory_snapshot: str = ""
    target_set_num: str = ""
    mode: Mode = "exact"
    message: str = ""
    greedy_copy_count: int = 0

    @property
    def dismantling_count(self):
        return len(self.selected_copy_ids)


def _allocate(required, sources, mode):
    """Reserve exact colors globally before using any alternate colors."""
    remaining = {s: Counter(bag) for s, bag in sources.items()}
    deficits = Counter(required)
    rows = []
    for exact_pass in (True, False):
        if not exact_pass and mode == "exact":
            break
        for (part, requested), deficit in sorted(deficits.items()):
            for source, bag in remaining.items():
                colors = [requested] if exact_pass else sorted(c for p, c in bag if p == part and c != requested)
                for supplied in colors:
                    used = min(bag[part, supplied], deficit)
                    if used:
                        rows.append(Allocation(part, requested, supplied, used, source))
                        bag[part, supplied] -= used
                        deficit -= used
                        deficits[part, requested] -= used
    if any(deficits.values()):
        raise ValueError("Allocation cannot supply the complete target")
    return rows


def _coverage(required, sources, mode):
    bag = Counter()
    for source in sources.values():
        bag.update(source)
    return matched_quantity(bag, required) if mode == "exact" else matched_quantity(by_part(bag), by_part(required))


def _greedy(required, sources, mode):
    selected = {"loose": sources.get("loose", Counter())}
    remaining = {s: bag for s, bag in sources.items() if s != "loose"}
    covered = _coverage(required, selected, mode)
    while covered < sum(required.values()):
        if not remaining:
            raise ValueError("No complete greedy plan")
        source = max(remaining, key=lambda s: _coverage(required, {**selected, s: remaining[s]}, mode) - covered)
        selected[source] = remaining.pop(source)
        covered = _coverage(required, selected, mode)
    return _allocate(required, selected, mode)


def validate_allocations(required, sources, allocations, selected_copy_ids, mode):
    """Independent capacity and demand check; never trust solver output implicitly."""
    supplied = Counter()
    requested = Counter()
    used_copies = set()
    for row in allocations:
        if type(row.quantity) is not int or row.quantity <= 0:
            raise ValueError("Invalid allocation quantity")
        key = (row.part_id, row.requested_color)
        if key not in required or row.source_id not in sources:
            raise ValueError("Unknown allocation source or requested part")
        if mode == "exact" and row.requested_color != row.supplied_color:
            raise ValueError("Unexpected color substitution")
        supplied[row.source_id, row.part_id, row.supplied_color] += row.quantity
        requested[key] += row.quantity
        if row.source_id != "loose":
            used_copies.add(row.source_id)
    if requested != Counter(required):
        raise ValueError("Allocations do not exactly satisfy target quantities")
    for (source, part, color), count in supplied.items():
        if count > sources[source].get((part, color), 0):
            raise ValueError("Source inventory was double-counted")
    if len(selected_copy_ids) != len(set(selected_copy_ids)) or used_copies != set(selected_copy_ids):
        raise ValueError("Selected physical copies do not match allocations")


def _finish(plan, rows, required, sources, started, *, optimal=False):
    ids = sorted({r.source_id for r in rows if r.source_id != "loose"})
    validate_allocations(required, sources, rows, ids, plan.mode)
    plan.allocations, plan.selected_copy_ids = rows, ids
    plan.minimum_proven = optimal
    plan.status = "optimal" if optimal else "feasible"
    plan.color_substitutions = sum(r.quantity for r in rows if r.requested_color != r.supplied_color)
    plan.elapsed_seconds = perf_counter() - started
    plan.message = "Minimum dismantling proven." if optimal else "Best plan found; minimum not proven."
    return plan


def inventory_snapshot(catalog, collection, mode):
    return hashlib.sha256(f"{catalog_fingerprint(catalog)}:{collection.snapshot(mode)}".encode()).hexdigest()


def plan_build(catalog, collection: CollectionState, target_set_num: str, mode: Mode,
               time_limit_seconds: float = 5.0) -> BuildPlan:
    started = perf_counter()
    plan = BuildPlan("error", False, inventory_snapshot=inventory_snapshot(catalog, collection, mode),
                     target_set_num=target_set_num, mode=mode)
    try:
        if mode not in ("exact", "flexible"):
            raise ValueError("Unknown matching mode")
        if not math.isfinite(time_limit_seconds) or time_limit_seconds < 0:
            raise ValueError("Time limit must be finite and nonnegative")
        required = catalog.inventory(target_set_num)
        if not required or any(type(n) is not int or n <= 0 for n in required.values()):
            raise ValueError("Target inventory is empty or invalid")
        sources = inventory_sources(catalog, collection, planner=True)
        available = Counter()
        for bag in sources.values():
            available.update(bag)
        all_available = available_inventory(catalog, collection)
        need = required if mode == "exact" else by_part(required)
        have = available if mode == "exact" else by_part(available)
        all_have = all_available if mode == "exact" else by_part(all_available)
        for key, quantity in sorted(need.items()):
            deficit = max(0, quantity - have[key])
            if deficit:
                part, color = key if mode == "exact" else (key, None)
                plan.shortages.append(Shortage(part, color, deficit, min(deficit, all_have[key] - have[key])))
        if plan.shortages:
            plan.status = "insufficient inventory"
            plan.message = "A complete plan is unavailable. Protected copies contribute to recommendations only."
            plan.elapsed_seconds = perf_counter() - started
            return plan
        parts = {p for p, _ in required}
        sources = {s: Counter({k: n for k, n in bag.items()
                               if k in required or (mode == "flexible" and k[0] in parts)})
                   for s, bag in sources.items()}
        sources = {s: bag for s, bag in sources.items() if bag or s == "loose"}
        baseline = _greedy(required, sources, mode)
        baseline_ids = sorted({r.source_id for r in baseline if r.source_id != "loose"})
        validate_allocations(required, sources, baseline, baseline_ids, mode)
        plan.greedy_copy_count = len(baseline_ids)
        if not baseline_ids:
            return _finish(plan, baseline, required, sources, started, optimal=True)
        if time_limit_seconds == 0:
            return _finish(plan, baseline, required, sources, started)

        model = cp_model.CpModel()
        selected = {s: model.new_bool_var(f"copy_{s}") for s in sources if s != "loose"}
        flows, demands, capacities = {}, defaultdict(list), defaultdict(list)
        substitutions = []
        for source, bag in sources.items():
            by_id = defaultdict(list)
            for part, color in sorted(bag):
                by_id[part].append(color)
            for (part, requested), quantity in sorted(required.items()):
                for supplied in by_id[part]:
                    if mode == "exact" and supplied != requested:
                        continue
                    capacity = bag[part, supplied]
                    variable = model.new_int_var(0, min(quantity, capacity), f"flow_{len(flows)}")
                    flows[source, part, requested, supplied] = variable
                    demands[part, requested].append(variable)
                    capacities[source, part, supplied].append(variable)
                    if supplied != requested:
                        substitutions.append(variable)
        for key, quantity in required.items():
            model.add(sum(demands[key]) == quantity)
        for (source, part, color), variables in capacities.items():
            capacity = sources[source][part, color]
            model.add(sum(variables) <= (capacity if source == "loose" else capacity * selected[source]))
        weight = sum(required.values()) + 1
        model.minimize(weight * sum(selected.values()) + sum(substitutions))
        hints = Counter()
        for row in baseline:
            hints[row.source_id, row.part_id, row.requested_color, row.supplied_color] += row.quantity
        for key, variable in flows.items():
            model.add_hint(variable, hints[key])
        for source, variable in selected.items():
            model.add_hint(variable, int(source in baseline_ids))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_seconds
        solver.parameters.random_seed = 0
        solver.parameters.num_search_workers = 1
        status = solver.solve(model)
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            rows = [Allocation(part, requested, supplied, solver.value(v), source)
                    for (source, part, requested, supplied), v in flows.items() if solver.value(v)]
            # A short search must never return a worse plan than our complete baseline.
            objective = lambda rs: weight * len({r.source_id for r in rs if r.source_id != "loose"}) + sum(
                r.quantity for r in rs if r.requested_color != r.supplied_color)
            if objective(baseline) < objective(rows):
                rows = baseline
                status = cp_model.FEASIBLE
            return _finish(plan, rows, required, sources, started, optimal=status == cp_model.OPTIMAL)
        if status == cp_model.UNKNOWN:
            return _finish(plan, baseline, required, sources, started)
        raise ValueError("Optimizer rejected a model with a known complete baseline")
    except Exception as error:
        plan.status, plan.minimum_proven = "error", False
        plan.allocations, plan.selected_copy_ids = [], []
        plan.message = f"Could not plan this build: {error}"
        plan.elapsed_seconds = perf_counter() - started
        return plan
