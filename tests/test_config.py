import pytest
from pydantic import ValidationError

from multiqc_pivot.config import Level
from multiqc_pivot.config import SamplePivotConfig

GROUP = r"^(?P<group>\d+)\."


def test_defaults() -> None:
    settings = SamplePivotConfig(group=GROUP, levels=[Level(match=r"\.subject$")])
    assert settings.column_title == "{Label} {title}"
    assert settings.label_order == []
    assert settings.tables == {}
    assert settings.group_pattern.search("101.subject") is not None


def test_from_mapping() -> None:
    settings = SamplePivotConfig.model_validate({
        "group": GROUP,
        "levels": [
            {"match": r"\.subject$"},
            {"match": r"\.(?P<analyte>tissueA|tissueB)$", "label": "{analyte}"},
            {"match": r"\.library\.", "table": "Library statistics"},
        ],
        "label_order": ["tissueA", "tissueB"],
        "tables": {"Library statistics": {"description": "Per-library QC"}},
    })
    assert [level.label for level in settings.levels] == [None, "{analyte}", None]
    assert settings.levels[2].table == "Library statistics"
    assert settings.tables["Library statistics"].description == "Per-library QC"


def test_group_requires_named_capture() -> None:
    with pytest.raises(ValidationError, match="named capture"):
        SamplePivotConfig(group=r"^(\d+)\.", levels=[Level(match=r"\.subject$")])


def test_at_least_one_level() -> None:
    with pytest.raises(ValidationError, match="at least 1"):
        SamplePivotConfig(group=GROUP, levels=[])


def test_invalid_regular_expression() -> None:
    with pytest.raises(ValidationError, match="regular expression"):
        Level(match="(")
    with pytest.raises(ValidationError, match="regular expression"):
        SamplePivotConfig(group="(?P<group>", levels=[Level(match=r"\.x$")])


def test_label_and_table_are_exclusive() -> None:
    with pytest.raises(ValidationError, match="not both"):
        Level(match=r"\.x$", label="x", table="Table")


def test_label_must_use_captures_of_match() -> None:
    with pytest.raises(ValidationError, match="lacks"):
        Level(match=r"\.(?P<analyte>x)$", label="{tissue}")
    assert Level(match=r"\.(?P<analyte>x)$", label="{analyte} (filtered)").label is not None


def test_column_title_placeholders() -> None:
    with pytest.raises(ValidationError, match="column_title"):
        SamplePivotConfig(group=GROUP, levels=[Level(match=r"\.x$")], column_title="{nope}")
    settings = SamplePivotConfig(
        group=GROUP, levels=[Level(match=r"\.x$")], column_title="{title} ({label})"
    )
    assert settings.column_title == "{title} ({label})"


def test_unknown_keys_are_rejected() -> None:
    with pytest.raises(ValidationError, match="extra"):
        SamplePivotConfig.model_validate({"group": GROUP, "levels": [{"match": "x"}], "order": []})
