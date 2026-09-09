"""Settings for the `sample_pivot` block of a MultiQC configuration."""

from __future__ import annotations

import re
from typing import ClassVar

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

GROUP_CAPTURE = "group"
"""The named capture the group pattern must define; its value names the folded row."""


def _compile(pattern: str, where: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"{where} is not a valid regular expression: {pattern!r} ({exc})") from exc


class Level(BaseModel):
    """
    One kind of sample name and what happens to the rows that carry it.

    A level with neither `label` nor `table` folds its columns onto the group row as they are. A
    level with a `label` renames its columns after the label, folds them onto the group row and
    keeps the original row underneath. A level with a `table` moves its rows out of General
    Statistics into a table of that name, keeping whatever grouping they already had.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    match: str
    label: str | None = None
    table: str | None = None

    @field_validator("match")
    @classmethod
    def _match_compiles(cls, value: str) -> str:
        return _compile(value, "match").pattern

    @model_validator(mode="after")
    def _label_or_table(self) -> Level:
        if self.label is not None and self.table is not None:
            raise ValueError("a level may set label or table, not both")
        if self.label is not None:
            captures = dict.fromkeys(self.pattern.groupindex, "")
            try:
                _ = self.label.format(**captures)
            except (KeyError, IndexError) as exc:
                message = f"label {self.label!r} uses a capture that match {self.match!r} lacks"
                raise ValueError(f"{message} ({exc})") from exc
        return self

    @property
    def pattern(self) -> re.Pattern[str]:
        """The compiled `match` expression."""
        return re.compile(self.match)


class TableSettings(BaseModel):
    """How a table that receives rows moved out of General Statistics presents itself."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    description: str = ""


class SamplePivotConfig(BaseModel):
    """The `sample_pivot` block of a MultiQC configuration."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    group: str
    levels: list[Level] = Field(min_length=1)
    column_title: str = "{Label} {title}"
    label_order: list[str] = Field(default_factory=list)
    tables: dict[str, TableSettings] = Field(default_factory=dict)

    @field_validator("group")
    @classmethod
    def _group_has_capture(cls, value: str) -> str:
        if GROUP_CAPTURE not in _compile(value, "group").groupindex:
            raise ValueError(
                f"group must contain a named capture (?P<{GROUP_CAPTURE}>...): {value!r}"
            )
        return value

    @field_validator("column_title")
    @classmethod
    def _column_title_placeholders(cls, value: str) -> str:
        try:
            _ = value.format(label="", Label="", title="")
        except (KeyError, IndexError) as exc:
            raise ValueError(
                f"column_title may only use {{label}}, {{Label}} and {{title}}: {value!r} ({exc})"
            ) from exc
        return value

    @property
    def group_pattern(self) -> re.Pattern[str]:
        """The compiled `group` expression."""
        return re.compile(self.group)
