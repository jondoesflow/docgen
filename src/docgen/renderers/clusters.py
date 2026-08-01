"""Functional-cluster heuristic: group entities by relationship connectivity.

Hub entities (users, teams, currencies...) are excluded from edges because they
connect to nearly everything and would merge all clusters into one. Components
larger than MAX_CLUSTER_SIZE are split by iteratively pulling out the
highest-degree entity — simple and explainable to a consultant reading the LLD.
"""

from __future__ import annotations

from dataclasses import dataclass

from docgen.snapshot.models import Snapshot

HUB_ENTITIES = {"systemuser", "team", "businessunit", "transactioncurrency", "organization"}
MAX_CLUSTER_SIZE = 12


@dataclass
class Cluster:
    name: str
    entities: list[str]  # logical names, sorted


def _components(nodes: set[str], edges: dict[str, set[str]]) -> list[set[str]]:
    seen: set[str] = set()
    result = []
    for start in sorted(nodes):
        if start in seen:
            continue
        component = {start}
        stack = [start]
        while stack:
            current = stack.pop()
            for neighbour in edges.get(current, ()):  # only in-solution neighbours
                if neighbour in nodes and neighbour not in component:
                    component.add(neighbour)
                    stack.append(neighbour)
        seen |= component
        result.append(component)
    return result


def functional_clusters(snapshot: Snapshot) -> list[Cluster]:
    nodes = {e.logical_name for e in snapshot.entities}
    edges: dict[str, set[str]] = {n: set() for n in nodes}
    for entity in snapshot.entities:
        for rel in entity.relationships:
            a, b = rel.referenced_entity, rel.referencing_entity
            if a in HUB_ENTITIES or b in HUB_ENTITIES or a == b:
                continue
            if a in nodes and b in nodes:
                edges[a].add(b)
                edges[b].add(a)

    display = {e.logical_name: (e.display_name or e.logical_name) for e in snapshot.entities}

    def degree(node: str, members: set[str]) -> int:
        return len(edges.get(node, set()) & members)

    clusters: list[Cluster] = []
    for component in _components(nodes, edges):
        pending = [component]
        while pending:
            members = pending.pop()
            if len(members) > MAX_CLUSTER_SIZE:
                hub = max(sorted(members), key=lambda n: degree(n, members))
                rest = members - {hub}
                clusters.append(Cluster(name=display[hub], entities=[hub]))
                pending.extend(_components(rest, edges))
                continue
            anchor = max(sorted(members), key=lambda n: degree(n, members))
            clusters.append(Cluster(name=display[anchor], entities=sorted(members)))
    clusters.sort(key=lambda c: (-len(c.entities), c.name))
    return clusters
