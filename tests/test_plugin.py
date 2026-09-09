import importlib.metadata
import re
from pathlib import Path

import multiqc
from multiqc import config
from multiqc import report

from multiqc_pivot.config import TableSettings
from multiqc_pivot.pivot import Table
from multiqc_pivot.plugin import PACKAGE
from multiqc_pivot.plugin import after_modules
from multiqc_pivot.plugin import execution_start
from multiqc_pivot.plugin import table_module

DATA = Path(__file__).parent / "data"


def test_hooks_are_registered_as_entry_points() -> None:
    hooks = {
        (point.name, point.value)
        for point in importlib.metadata.entry_points(group="multiqc.hooks.v1")
        if point.value.startswith("multiqc_pivot.")
    }
    assert hooks == {
        ("execution_start", "multiqc_pivot.plugin:execution_start"),
        ("after_modules", "multiqc_pivot.plugin:after_modules"),
    }


def test_execution_start_records_the_version() -> None:
    execution_start()
    version = importlib.metadata.version(PACKAGE)
    assert config.software_versions[PACKAGE] == {PACKAGE: [version]}


def test_after_modules_without_settings_changes_nothing() -> None:
    multiqc.reset()  # type: ignore[no-untyped-call]
    config.update({"sample_pivot": None})
    after_modules()
    assert report.general_stats_data == {}


def test_report(tmp_path: Path) -> None:
    multiqc.reset()  # type: ignore[no-untyped-call]
    multiqc.parse_logs(str(DATA / "report"), config_files=[str(DATA / "multiqc_config.yml")])

    groups = {str(group) for section in report.general_stats_data.values() for group in section}
    assert groups == {"101", "102"}
    titles = {
        str(column.get("title"))
        for section in report.general_stats_headers.values()
        for column in section.values()
    }
    assert {
        "Concordance",
        "TissueA Median",
        "TissueB Median",
        "TissueB (filtered) % Aligned",
    } <= titles
    assert report.modules[0].name == "Library statistics"

    multiqc.write_report(output_dir=str(tmp_path), filename="report.html", force=True)
    html = (tmp_path / "report.html").read_text()
    general_stats = re.search(r'<table id="general_stats_table_table".*?</table>', html, re.S)
    assert general_stats is not None
    assert general_stats.group(0).count('class="expandable-row-primary"') == 2
    assert "TissueA Median" in general_stats.group(0)
    assert ".library." not in general_stats.group(0)
    library_stats = re.search(r'<table id="library_statistics_table_table".*?</table>', html, re.S)
    assert library_stats is not None
    assert library_stats.group(0).count('<tr data-sample-group="101.tissueA.library.L1"') == 1
    assert html.count("Per-library read QC.") == 1


def test_table_module_is_none_for_an_empty_table() -> None:
    assert table_module("Empty", TableSettings(), Table()) is None
