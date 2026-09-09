import logging
from typing import Iterator
from typing import List
from typing import Optional

import pytest
from multiqc.plots.table_object import ColumnDict
from multiqc.plots.table_object import InputRow
from multiqc.plots.table_object import ValueT
from multiqc.types import ColumnKey
from multiqc.types import SampleGroup
from multiqc.types import SampleName
from multiqc.types import SectionKey

from multiqc_pivot.config import Level
from multiqc_pivot.config import SamplePivotConfig
from multiqc_pivot.pivot import PLACEMENT_BLOCK
from multiqc_pivot.pivot import Folded
from multiqc_pivot.pivot import Moved
from multiqc_pivot.pivot import Placement
from multiqc_pivot.pivot import classify
from multiqc_pivot.pivot import pivot
from multiqc_pivot.pivot import slug

SETTINGS = SamplePivotConfig(
    group=r"^(?P<group>\d+)\.",
    levels=[
        Level(match=r"\.subject$"),
        Level(match=r"\.(?P<analyte>tissueA|tissueB)$", label="{analyte}"),
        Level(match=r"\.(?P<analyte>tissueA|tissueB) \(filtered\)$", label="{analyte} (filtered)"),
        Level(match=r"\.library\.", table="Library statistics"),
    ],
    label_order=["tissueA", "tissueB"],
)


def row(sample: str, **data: Optional[ValueT]) -> InputRow:
    return InputRow(sample=SampleName(sample), data={ColumnKey(k): v for k, v in data.items()})


def section(*rows: InputRow) -> dict[SampleGroup, List[InputRow]]:
    return {SampleGroup(str(r.sample)): [r] for r in rows}


def header(title: str, **extra: object) -> ColumnDict:
    return {"title": title, **extra}  # type: ignore[typeddict-item]


@pytest.fixture
def warnings() -> Iterator[List[str]]:
    messages: List[str] = []

    class Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    handler = Collect(level=logging.WARNING)
    logger = logging.getLogger("multiqc")
    logger.addHandler(handler)
    yield messages
    logger.removeHandler(handler)


def test_classify() -> None:
    assert classify("101.subject", SETTINGS) == Folded("101")
    assert classify("101.tissueA", SETTINGS) == Folded("101", "tissueA")
    assert classify("101.tissueB (filtered)", SETTINGS) == Folded("101", "tissueB (filtered)")
    assert classify("101.tissueA.library.L1", SETTINGS) == Moved("Library statistics")
    assert classify("control", SETTINGS) is None


def test_classify_without_group_is_left_alone(warnings: List[str]) -> None:
    assert classify("abc.tissueA", SETTINGS) is None
    assert warnings == [
        "sample_pivot: 'abc.tissueA' matches '\\\\.(?P<analyte>tissueA|tissueB)$' but not the"
        " group; left as is"
    ]


def test_slug() -> None:
    assert slug("tissueB (filtered)") == "tissueb_filtered"
    assert slug("TissueA library R1") == "tissuea_library_r1"


def test_placement_follows_configured_order_then_first_seen() -> None:
    placement = Placement(["tissueA", "tissueB"])
    assert placement.next("tissueB") == 2 * PLACEMENT_BLOCK + 1
    assert placement.next("tissueA") == PLACEMENT_BLOCK + 2
    assert placement.next("tissueB (filtered)") == 3 * PLACEMENT_BLOCK + 3
    assert placement.next("tissueB (filtered)") == 3 * PLACEMENT_BLOCK + 4


def test_labelled_rows_fold_into_one_row_per_group() -> None:
    coverage = SectionKey("coverage")
    rows = {
        coverage: section(
            row("101.tissueA", median=743, undeclared=1),
            row("101.tissueB", median=419),
            row("102.tissueB", median=444),
        )
    }
    headers = {coverage: {ColumnKey("median"): header("Median", suffix="X", namespace="Coverage")}}

    result = pivot(rows, headers, SETTINGS)

    assert result.tables == {}
    assert list(result.rows[coverage]) == ["101", "102"]
    assert result.rows[coverage][SampleGroup("101")] == [
        row("101", median__tissuea=743, median__tissueb=419),
        row("101.tissueA", median__tissuea=743),
        row("101.tissueB", median__tissueb=419),
    ]
    assert result.rows[coverage][SampleGroup("102")] == [
        row("102", median__tissueb=444),
        row("102.tissueB", median__tissueb=444),
    ]
    new_headers = result.headers[coverage]
    assert set(new_headers) == {"median", "median__tissuea", "median__tissueb"}
    assert new_headers[ColumnKey("median__tissuea")] == {
        "title": "TissueA Median",
        "suffix": "X",
        "namespace": "Coverage",
        "placement": PLACEMENT_BLOCK + 1,
    }
    assert new_headers[ColumnKey("median__tissueb")]["title"] == "TissueB Median"
    assert new_headers[ColumnKey("median__tissueb")]["placement"] == 2 * PLACEMENT_BLOCK + 2
    assert new_headers[ColumnKey("median")] == headers[coverage][ColumnKey("median")]


def test_unlabelled_rows_become_the_group_row() -> None:
    concordance = SectionKey("concordance")
    rows = {concordance: section(row("101.subject", concordance=99.7, undeclared="x"))}
    headers = {concordance: {ColumnKey("concordance"): header("Concordance")}}

    result = pivot(rows, headers, SETTINGS)

    assert result.rows[concordance] == {SampleGroup("101"): [row("101", concordance=99.7)]}
    assert result.headers[concordance] == headers[concordance]


def test_table_levels_move_rows_with_their_grouping() -> None:
    fastqc = SectionKey("fastqc")
    library = SampleGroup("101.tissueA.library.L1")
    grouped = [
        row("101.tissueA.library.L1", dups=70.0),
        row("101.tissueA.library.L1 R1", dups=71.0),
        row("101.tissueA.library.L1 R2", dups=69.0),
    ]
    rows = {fastqc: {library: grouped}}
    headers = {fastqc: {ColumnKey("dups"): header("Dups")}}

    result = pivot(rows, headers, SETTINGS)

    assert result.rows[fastqc] == {}
    assert result.headers[fastqc] == headers[fastqc]
    table = result.tables["Library statistics"]
    assert table.rows == {fastqc: {library: grouped}}
    assert table.headers == headers


def test_unmatched_rows_are_untouched() -> None:
    other = SectionKey("other")
    rows = {other: section(row("control", median=1))}
    headers = {other: {ColumnKey("median"): header("Median")}}

    result = pivot(rows, headers, SETTINGS)

    assert result.rows == rows
    assert result.headers == headers


def test_column_title_format() -> None:
    settings = SETTINGS.model_copy(update={"column_title": "{title} ({label})"})
    coverage = SectionKey("coverage")
    rows = {coverage: section(row("101.tissueB (filtered)", aligned=35.4))}
    headers = {coverage: {ColumnKey("aligned"): header("% Aligned")}}

    result = pivot(rows, headers, settings)

    assert result.headers[coverage][ColumnKey("aligned__tissueb_filtered")]["title"] == (
        "% Aligned (tissueB (filtered))"
    )


def test_conflicting_values_keep_the_first(warnings: List[str]) -> None:
    settings = SETTINGS.model_copy(
        update={"levels": [Level(match=r"\.(?P<analyte>tissueA)", label="{analyte}")]}
    )
    coverage = SectionKey("coverage")
    rows = {coverage: section(row("101.tissueA", median=743), row("101.tissueA2", median=1))}
    headers = {coverage: {ColumnKey("median"): header("Median")}}

    result = pivot(rows, headers, settings)

    assert result.rows[coverage][SampleGroup("101")][0] == row("101", median__tissuea=743)
    assert warnings == [
        "sample_pivot: group '101' has two values for 'median__tissuea'; keeping the first"
    ]


def test_missing_headers_leave_rows_untouched_in_place() -> None:
    coverage = SectionKey("coverage")
    rows = {coverage: section(row("101.tissueA", median=743))}

    result = pivot(rows, {}, SETTINGS)

    assert result.rows[coverage] == {
        SampleGroup("101"): [row("101"), row("101.tissueA")],
    }
    assert result.headers == {coverage: {}}
