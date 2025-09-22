from argparse import Namespace
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum, auto
from functools import partial
from graphlib import TopologicalSorter
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass
class Derived:
    fn: Callable
    prev: set[str]
    final: set[str]


def derived(*, prev: set[str] | None = None, final: set[str] | None = None) -> Callable[[Callable], Derived]:
    return partial(Derived, prev=prev or set(), final=final or set())


class Required(Enum):
    REQUIRED = auto()


def required() -> Required:
    return Required.REQUIRED


class NotSet(Enum):
    NOT_SET = auto()


def not_set() -> NotSet:
    return NotSet.NOT_SET


class SettingResolver(Generic[T]):
    @staticmethod
    def iter_settings(namespace: Any) -> Iterable[str]:
        for name in dir(namespace):
            if name == name.upper() and not name.startswith("_"):
                yield name

    def __init__(self) -> None:
        self.layers: list[dict[str, T | Derived | Required | NotSet]] = []
        self.layers.append(defaultdict(not_set))  # base level: nothing is set

    def add_layer(self, namespace: Any) -> None:
        self.layers.append({name: getattr(namespace, name) for name in self.iter_settings(namespace)})

    @property
    def final_layer(self) -> int:
        return len(self.layers) - 1

    def all_setting_names(self) -> Iterable[str]:
        return {name for layer in self.layers for name in layer}

    def get_setting_at_layer(self, name, layer_index) -> T | Required | NotSet:
        for i in range(layer_index, 0, -1):
            if name in self.layers[i]:
                value = self.layers[i][name]
                assert not isinstance(value, Derived)
                return value
        return NotSet.NOT_SET

    def compute_derived_values(self) -> None:
        sorter = TopologicalSorter[tuple[int, str]]()

        for i, layer in enumerate(self.layers):
            for name, value in layer.items():
                deps: list[tuple[int, str]] = []
                if isinstance(value, Derived):
                    deps.extend((i - 1, dep_name) for dep_name in value.prev)
                    deps.extend((self.final_layer, dep_name) for dep_name in value.final)
                sorter.add((i, name), *deps)

        for index, name in sorter.static_order():
            match self.layers[index].get(name):
                case Derived(fn, prev, final):
                    prev_ns = Namespace(**{name: self.get_setting_at_layer(name, index - 1) for name in prev})
                    final_ns = Namespace(**{name: self.get_setting_at_layer(name, self.final_layer) for name in final})
                    self.layers[index][name] = fn(prev_ns, final_ns)

    def get_final_values(self, keys: Iterable[str]) -> dict[str, T]:
        resolved = {}
        missing_settings = set()
        for name in keys:
            value = self.get_setting_at_layer(name, self.final_layer)
            match value:
                case Derived():
                    raise AssertionError("derived values should have been resolved by now")
                case Required.REQUIRED:
                    missing_settings.add(name)
                case NotSet.NOT_SET:
                    pass
                case _:
                    resolved[name] = value
        if missing_settings:
            raise ValueError(f"The following settings must be set: {', '.join(missing_settings)}")
        return resolved

    def resolve(self) -> dict[str, T]:
        self.compute_derived_values()
        return self.get_final_values(self.all_setting_names())


def resolve_settings(namespaces: list[Any]) -> dict[str, Any]:
    resolver = SettingResolver[Any]()
    for ns in namespaces:
        resolver.add_layer(ns)
    return resolver.resolve()
