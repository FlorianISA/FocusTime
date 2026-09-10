"""Répartition aléatoire P9/P10, sans répétition de nom et selon les capacités."""

import random

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix
from activity_import import activity_name


class AllocationError(ValueError):
    pass


def allocate(roster, activities, assignments, rng=None):
    """Attribuer les périodes libres en privilégiant les dépassements à capacité limitée."""
    rng = rng or random.SystemRandom()
    activity_map = {a["id"]: a for a in activities}
    occupied = {(a["email"], a["period"]) for a in assignments}
    used = {
        (a["email"], activity_name(activity_map[a["activity_id"]]["name"]))
        for a in assignments
    }
    counts = {a["id"]: 0 for a in activities}
    for assignment in assignments:
        counts[assignment["activity_id"]] += 1
    missing = [
        (s["email"], p)
        for s in roster
        for p in (9, 10)
        if (s["email"], p) not in occupied
    ]
    if not missing:
        return []
    slot_index = {slot: i for i, slot in enumerate(missing)}
    groups = [a for a in activities if a["kind"] == "depassement"]
    variables, constraints, costs = [], [], []
    identity_index = {}
    for pupil in roster:
        for gi, activity in enumerate(groups):
            slot = (pupil["email"], activity["period"])
            identity = (pupil["email"], activity_name(activity["name"]))
            if (
                slot not in slot_index
                or pupil["degree"] != activity["degree"]
                or identity in used
            ):
                continue
            identity_index.setdefault(identity, len(identity_index))
            variables.append({"email": pupil["email"], "activity_id": activity["id"]})
            constraints.append((slot_index[slot], len(missing) + gi, identity))
            costs.append(
                float(activity["capacity"] is None)
                + rng.random() / (len(missing) + 1) * 0.01
            )
    if not variables:
        raise AllocationError(
            "Aucun dépassement compatible. Ajoutez une activité différente pour les périodes libres."
        )
    row_ids, col_ids, values = [], [], []
    for vi, (slot, group, identity) in enumerate(constraints):
        for row in (slot, group, len(missing) + len(groups) + identity_index[identity]):
            row_ids.append(row)
            col_ids.append(vi)
            values.append(1.0)
    lower = np.concatenate(
        (np.ones(len(missing)), np.zeros(len(groups) + len(identity_index)))
    )
    upper = np.concatenate(
        (
            np.ones(len(missing)),
            np.array(
                [
                    (
                        len(roster)
                        if a["capacity"] is None
                        else max(0, a["capacity"] - counts[a["id"]])
                    )
                    for a in groups
                ]
            ),
            np.ones(len(identity_index)),
        )
    )
    matrix = coo_matrix(
        (values, (row_ids, col_ids)), shape=(len(lower), len(variables))
    ).tocsc()
    result = milp(
        c=np.array(costs),
        integrality=np.ones(len(variables)),
        bounds=Bounds(0, 1),
        constraints=LinearConstraint(matrix, lower, upper),
        options={"time_limit": 30.0, "mip_rel_gap": 0.0},
    )
    if result.status == 2:
        raise AllocationError(
            "Impossible d'attribuer deux activités différentes à chaque élève avec les groupes disponibles. "
            "Une activité ne peut pas être suivie deux fois. "
            "Ajoutez un autre dépassement pour le degré concerné, puis réessayez."
        )
    if result.status != 0 or result.x is None:
        raise AllocationError(
            "Le calcul n'a pas abouti dans le délai prévu. Aucun changement enregistré ; relancez la génération."
        )
    chosen = np.rint(result.x)
    usage = matrix @ chosen
    if not (np.all(usage >= lower - 1e-7) and np.all(usage <= upper + 1e-7)):
        raise AllocationError("Le calcul n'a pas produit de plan complet valide.")
    return [variable for variable, selected in zip(variables, chosen) if selected == 1]
