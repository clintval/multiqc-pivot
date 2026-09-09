"""The functions MultiQC calls through the `multiqc.hooks.v1` entry points."""

from __future__ import annotations

import importlib.metadata
import logging
from typing import TYPE_CHECKING
from typing import cast

from multiqc_pivot.config import SamplePivotConfig
from multiqc_pivot.config import TableSettings

if TYPE_CHECKING:
    from multiqc.base_module import BaseMultiqcModule

    from multiqc_pivot.pivot import Table

log = logging.getLogger("multiqc")

PACKAGE = "multiqc-pivot"
CONFIG_KEY = "sample_pivot"
"""The top-level key of a MultiQC configuration that holds this plugin's settings."""


def execution_start() -> None:
    """Record the plugin version among the report's software versions."""
    from multiqc import config

    version = importlib.metadata.version(PACKAGE)
    config.software_versions.setdefault(PACKAGE, {})[PACKAGE] = [version]
    log.info(f"Loaded {PACKAGE} {version}")


def after_modules() -> None:
    """Regroup General Statistics as the `sample_pivot` block asks, if the configuration has one."""
    from multiqc import config
    from multiqc import report

    from multiqc_pivot.pivot import pivot

    raw = getattr(config, CONFIG_KEY, None)
    if not raw:
        return
    settings = SamplePivotConfig.model_validate(raw)
    result = pivot(report.general_stats_data, report.general_stats_headers, settings)
    report.general_stats_data.clear()
    report.general_stats_data.update(result.rows)
    report.general_stats_headers.clear()
    report.general_stats_headers.update(result.headers)
    for name in reversed(list(result.tables)):
        module = table_module(name, settings.tables.get(name, TableSettings()), result.tables[name])
        if module is not None:
            report.modules.insert(0, module)
    groups = {group for section in result.rows.values() for group in section}
    tables = f" and {len(result.tables)} extra table(s)" if result.tables else ""
    log.info(f"sample_pivot: General Statistics now has {len(groups)} rows{tables}")


def table_module(name: str, settings: TableSettings, table: Table) -> BaseMultiqcModule | None:
    """
    Wrap rows moved out of General Statistics in a module holding a single table section.

    The module carries the name and description so the report shows them once; the section itself
    is untitled. Returns None when the table would be empty.
    """
    from multiqc.base_module import BaseMultiqcModule
    from multiqc.plots import table as table_plot
    from multiqc.plots.table_object import SectionT
    from multiqc.types import Anchor
    from multiqc.types import SectionKey

    from multiqc_pivot.pivot import slug

    anchor = slug(name)
    plot = table_plot.plot_with_sections(
        data=cast(dict[SectionKey, SectionT], table.rows),
        headers=table.headers,
        pconfig={
            "id": f"{anchor}_table",
            "title": name,
            "save_file": True,
            "raw_data_fn": f"multiqc_{anchor}",
        },
    )
    if plot is None:
        return None
    module = BaseMultiqcModule(name=name, anchor=Anchor(anchor), info=settings.description)
    module.add_section(anchor=Anchor(f"{anchor}_section"), plot=plot)
    return module
