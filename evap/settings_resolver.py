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
    """A setting that is derived from other settings."""

    fn: Callable
    prev: set[str]
    final: set[str]


def derived(*, prev: set[str] | None = None, final: set[str] | None = None) -> Callable[[Callable], Derived]:
    """Decorator to create derived settings."""
    return partial(Derived, prev=prev or set(), final=final or set())


class Required(Enum):
    """Type for marking settings as required.

    The resolver throws an error if a setting is required in the final mapping of settings. Thus, a setting declared as
    required must be overwritten in a later layer."""
    REQUIRED = auto()


def required() -> Required:
    """Shorthand function to create a required setting."""
    return Required.REQUIRED


class NotSet(Enum):
    """Type for marking settings as not set, that is, for keeping Django's default value."""
    NOT_SET = auto()


def not_set() -> NotSet:
    """Shorthand function to create a not-set setting."""
    return NotSet.NOT_SET


class SettingResolver(Generic[T]):
    """Main class for setting resolution.

    By default, Django settings are configured in a module like
    ```python
    DEBUG = True
    DATADIR = Path("./data")
    STATIC_ROOT = DATADIR / "static_collected"
    ```

    This interface works for simple setups, but lacks some features that we desire. Most importantly, we want to declare
    a set of default settings that do not necessarily need to be changed when deploying EvaP. Some of these settings
    depend on other settings though, for example the STATIC_ROOT setting above depends on the DATADIR setting. If users
    would change the value of DATADIR, they would also have to reassign STATIC_ROOT accordingly.

    To resolve this issue, we provide the SettingResolver which takes setting modules and aggregates them into a final
    mapping of settings to pass to Django. Notably, the input modules to the resolver can explicitly declare
    dependencies between settings using the `@derived` decorator. Concretely, the settings are organized into different
    layers. Later layers overwrite previous settings. A derived setting can then declare a dependency on another setting
    value from either the previous layer (for example to append an entry to a list) or the final layer (for example to
    use a path overwritten by the user).

    To compute the final set of setting values, we form a dependency graph on the settings and layers and compute the
    according values in topological order.

    Note that the SettingResolver class is generic over the type of the setting values T, however we only use it below
    with T = Any. The type T is only used to track at what times values can still be derived.
    """

    @staticmethod
    def iter_settings(namespace: Any) -> Iterable[str]:
        """Filter for attributes with SCREAMING_SNAKE_CASE names."""
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

    def get_setting_at_layer(self, name, layer_index) -> tuple[int, T | Derived | Required | NotSet]:
        for i in range(layer_index, 0, -1):
            if name in self.layers[i]:
                return i, self.layers[i][name]
        return 0, NotSet.NOT_SET

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
            match self.get_setting_at_layer(name, index):
                case actual_index, Derived(fn, prev, final):
                    prev_ns = Namespace(**{name: self.get_setting_at_layer(name, actual_index - 1)[1] for name in prev})
                    final_ns = Namespace(
                        **{name: self.get_setting_at_layer(name, self.final_layer)[1] for name in final}
                    )
                    assert all(not isinstance(val, Derived) for val in vars(prev_ns).values())
                    assert all(not isinstance(val, Derived) for val in vars(final_ns).values())
                    self.layers[actual_index][name] = fn(prev=prev_ns, final=final_ns)

    def get_final_values(self, keys: Iterable[str]) -> dict[str, T]:
        resolved = {}
        missing_settings = set()
        for name in keys:
            _, value = self.get_setting_at_layer(name, self.final_layer)
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
