"""Fold related General Statistics rows into one row per group."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from dataclasses import field

from multiqc.plots.table_object import ColumnDict
from multiqc.plots.table_object import ColumnKeyT
from multiqc.plots.table_object import ExtValueT
from multiqc.plots.table_object import InputRow
from multiqc.types import ColumnKey
from multiqc.types import SampleGroup
from multiqc.types import SampleName
from multiqc.types import SectionKey

from multiqc_pivot.config import SamplePivotConfig

log = logging.getLogger("multiqc")

RowData = dict[ColumnKeyT, ExtValueT | None]
SectionRows = dict[SampleGroup, list[InputRow]]
SectionHeaders = dict[ColumnKey, ColumnDict]
Rows = dict[SectionKey, SectionRows]
Headers = dict[SectionKey, SectionHeaders]

PLACEMENT_BLOCK = 10_000
"""Pivoted columns for the n-th label are placed at n times this value plus a running index.

MultiQC orders General Statistics columns by their placement (1000 unless a module says otherwise),
so every label forms one contiguous block after all of the columns that were not pivoted.
"""


@dataclass
class Table:
    """Rows moved out of General Statistics, keyed the same way General Statistics is."""

    rows: Rows = field(default_factory=dict)
    headers: Headers = field(default_factory=dict)

    def add(
        self, section: SectionKey, group: SampleGroup, row: InputRow, headers: SectionHeaders
    ) -> None:
        """Move a row in, keeping its section and group."""
        self.rows.setdefault(section, {}).setdefault(group, []).append(row)
        if section not in self.headers:
            self.headers[section] = dict(headers)


@dataclass
class PivotResult:
    """What General Statistics becomes, plus any tables split off from it."""

    rows: Rows
    headers: Headers
    tables: dict[str, Table]


@dataclass(frozen=True)
class Moved:
    """The row belongs in a secondary table."""

    table: str


@dataclass(frozen=True)
class Folded:
    """The row belongs on a group's row, under a label unless it is the group's own row."""

    group: str
    label: str | None = None


Route = Moved | Folded


def classify(name: str, settings: SamplePivotConfig) -> Route | None:
    """
    Decide where a sample's row goes from the first level that matches its name.

    Returns None when no level matches, or when a level matches but the group pattern does not; the
    latter is logged, since it usually means the group pattern is too narrow.
    """
    for level in settings.levels:
        match = level.pattern.search(name)
        if match is None:
            continue
        if level.table is not None:
            return Moved(level.table)
        group = settings.group_pattern.search(name)
        if group is None:
            log.warning(
                f"sample_pivot: {name!r} matches {level.match!r} but not the group; left as is"
            )
            return None
        label = level.label.format(**match.groupdict()) if level.label is not None else None
        return Folded(group.group("group"), label)
    return None


def slug(text: str) -> str:
    """Lower-case a label to letters, digits and single underscores."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def capitalise(text: str) -> str:
    """Upper-case the first character only."""
    return text[:1].upper() + text[1:]


class Placement:
    """
    Hands out column placements that cluster pivoted columns by label.

    Labels follow the configured order; labels missing from it come afterwards in order of first
    appearance.
    """

    def __init__(self, order: list[str]) -> None:
        """Start from the configured label order."""
        self._order: list[str] = list(order)
        self._count: int = 0

    def next(self, label: str) -> float:
        """The placement for the next pivoted column of a label."""
        if label not in self._order:
            self._order.append(label)
        self._count += 1
        return float(PLACEMENT_BLOCK * (self._order.index(label) + 1) + self._count)


def pivoted_header(
    header: ColumnDict,
    key: ColumnKey,
    label: str,
    settings: SamplePivotConfig,
    placement: Placement,
) -> ColumnDict:
    """Copy a column header under a labelled title and a placement inside the label's block."""
    copy = header.copy()
    copy["title"] = settings.column_title.format(
        label=label, Label=capitalise(label), title=header.get("title", key)
    )
    copy["placement"] = placement.next(label)
    return copy


@dataclass
class SectionPivot:
    """Rebuilds one General Statistics section a row at a time."""

    headers: SectionHeaders
    settings: SamplePivotConfig
    placement: Placement
    new_headers: SectionHeaders = field(init=False)
    _kept: SectionRows = field(default_factory=dict)
    _group_rows: dict[str, RowData] = field(default_factory=dict)
    _sub_rows: dict[str, list[InputRow]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Start from the module's own headers; pivoted columns are added alongside them."""
        self.new_headers = dict(self.headers)

    def keep(self, group: SampleGroup, row: InputRow) -> None:
        """Leave a row where it was."""
        self._kept.setdefault(group, []).append(row)

    def fold(self, group: str, row: InputRow) -> None:
        """Put a row's declared columns onto the group row as they are; the row itself goes away."""
        target = self._group_rows.setdefault(group, {})
        for key, value in row.data.items():
            if key in self.headers:
                _fold(target, key, value, group)

    def fold_labelled(self, group: str, label: str, row: InputRow) -> None:
        """
        Rename a row's declared columns after the label and put them onto the group row.

        The row itself stays beneath the group row, carrying the same renamed columns.
        """
        target = self._group_rows.setdefault(group, {})
        renamed: RowData = {}
        for key, value in row.data.items():
            if key not in self.headers:
                continue
            new_key = ColumnKey(f"{key}__{slug(label)}")
            if new_key not in self.new_headers:
                self.new_headers[new_key] = pivoted_header(
                    self.headers[key], key, label, self.settings, self.placement
                )
            renamed[new_key] = value
            _fold(target, new_key, value, group)
        self._sub_rows.setdefault(group, []).append(InputRow(sample=row.sample, data=renamed))

    def finish(self) -> SectionRows:
        """The rebuilt rows, each group row first with its folded rows beneath."""
        for name in dict.fromkeys([*self._group_rows, *self._sub_rows]):
            group = SampleGroup(name)
            first = InputRow(sample=SampleName(name), data=self._group_rows.get(name, {}))
            self._kept[group] = [first, *self._sub_rows.get(name, []), *self._kept.get(group, [])]
        return self._kept


def pivot(rows: Rows, headers: Headers, settings: SamplePivotConfig) -> PivotResult:
    """
    Rebuild General Statistics with one row per group.

    Rows that match a labelled level have their declared columns renamed after the label and copied
    onto the group's row; the original rows stay beneath it so the group can still be expanded.
    Rows that match an unlabelled level are folded onto the group's row as they are. Rows that match
    a level with a table are moved into that table with their grouping intact; the tables come back
    in the order their levels are listed, without the ones that received no rows. Rows that match no
    level, and columns a module did not declare a header for, are left alone.
    """
    placement = Placement(settings.label_order)
    out_rows: Rows = {}
    out_headers: Headers = {}
    tables = {level.table: Table() for level in settings.levels if level.table is not None}
    for section, rows_by_group in rows.items():
        section_headers = headers.get(section, {})
        pivoted = SectionPivot(section_headers, settings, placement)
        for group, members in rows_by_group.items():
            for row in members:
                route = classify(str(row.sample), settings)
                if route is None:
                    pivoted.keep(group, row)
                elif isinstance(route, Moved):
                    tables[route.table].add(section, group, row, section_headers)
                elif route.label is None:
                    pivoted.fold(route.group, row)
                else:
                    pivoted.fold_labelled(route.group, route.label, row)
        out_rows[section] = pivoted.finish()
        out_headers[section] = pivoted.new_headers
    return PivotResult(out_rows, out_headers, {n: t for n, t in tables.items() if t.rows})


def _fold(target: RowData, key: ColumnKeyT, value: ExtValueT | None, group: str) -> None:
    if key in target and target[key] != value:
        log.warning(f"sample_pivot: group '{group}' has two values for '{key}'; keeping the first")
        return
    target[key] = value
