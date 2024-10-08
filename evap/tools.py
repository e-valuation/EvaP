import datetime
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypeVar

Key = TypeVar("Key")
Value = TypeVar("Value")
T = TypeVar("T")


@dataclass
class MonthAndDay:
    month: int
    day: int


def unordered_groupby(key_value_pairs: Iterable[tuple[Key, Value]]) -> dict[Key, list[Value]]:
    """
    We need this in several places: Take list of (key, value) pairs and make
    them into the aggregated all-values-of-every-unique-key dict. Note that
    this slightly differs from itertools.groupby (and uniq), as we don't
    require anything to be sorted and you get a dict as return value.
    """
    result = defaultdict(list)
    for key, value in key_value_pairs:
        result[key].append(value)

    return dict(result)


def date_to_datetime(date: datetime.date) -> datetime.datetime:
    return datetime.datetime(year=date.year, month=date.month, day=date.day)


def ilen(iterable: Iterable) -> int:
    return sum(1 for _ in iterable)


def assert_not_none(value: T | None) -> T:
    assert value is not None
    return value
