from typing import Any
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import partial
from graphlib import TopologicalSorter


@dataclass
class Derived:
    fn: Callable
    prev: set[str]
    final: set[str]


def derived(*, prev: set[str] | None = None, final: set[str] | None = None) -> Callable[[Callable], Derived]:
    return partial(Derived, prev=prev or set(), final=final or set())


@dataclass
class UnresolvedSetting:
    fn: Callable
    dependencies: set[tuple[str, int]] = field(default_factory=set)


def required():
    pass


def dependent(fn):
    pass


def iter_settings(namespace: Any) -> Iterable[str]:
    return []


def resolve(layers: list[Any]) -> dict[str, Any]:
    sorter = TopologicalSorter[Any]()

    unresolved = [{} for _ in range(len(layers))]
    FINAL = object()

    for index, layer in enumerate(layers):
        for name in iter_settings(layer):
            item = getattr(layer, name)
            unresolved[index][name] = item

            if isinstance(item, Derived):
                deps = set()
                for dep_name in item.prev:
                    deps.add((max(i for i in range(index) if dep_name in unresolved[i]), dep_name))
                for dep_name in item.final:
                    deps.add((FINAL, dep_name))
                sorter.add((index, name), *deps)
            else:
                sorter.add((index, name))

    for name, unresolved_settings in unresolved.items():
        for i, setting in enumerate(unresolved_settings):
            if isinstance(setting, UnresolvedSetting):
                sorter.add(
                    (name, i),
                    *(
                        (name, index) if index != -1 else (name, len(unresolved[name]) - 1)
                        for dep_name, index in setting.dependencies
                    ),
                )
            else:
                sorter.add((name, i))

    resolved: dict[str, Any] = {}
    for name, index in sorter.static_order():
        pass
    return resolved
