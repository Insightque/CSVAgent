"""Click CLI for CSVAgent."""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import click
import pandas as pd

from .config_manager import ConfigManager
from .data_analyzer import DataAnalyzer
from .exceptions import CSVAgentError, ConfigurationError
from .file_manager import FileManager

SUPPORTED_NUMERIC_CHARTS = {"histogram", "line", "box"}
SUPPORTED_CATEGORICAL_CHARTS = {"bar", "pie"}
SUPPORTED_CHARTS = SUPPORTED_NUMERIC_CHARTS | SUPPORTED_CATEGORICAL_CHARTS


@dataclass(slots=True)
class AppContext:
    """Shared application services."""

    config_manager: ConfigManager
    file_manager: FileManager
    analyzer: DataAnalyzer


def handle_cli_errors(command: Any) -> Any:
    """Convert internal exceptions into Click-friendly output."""

    @functools.wraps(command)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return command(*args, **kwargs)
        except ModuleNotFoundError as exc:
            dependency_name = exc.name or "required dependency"
            raise click.ClickException(
                f"Missing dependency '{dependency_name}'. "
                "Install packages from requirements.txt before using this command."
            ) from exc
        except ImportError as exc:
            raise click.ClickException(str(exc)) from exc
        except CSVAgentError as exc:
            raise click.ClickException(str(exc)) from exc
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        except OSError as exc:
            raise click.ClickException(str(exc)) from exc

    return wrapper


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--config-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Override the default JSON config path.",
)
@click.pass_context
def cli(ctx: click.Context, config_path: Path | None) -> None:
    """CSVAgent: inspect CSV files and create interactive plotly charts."""
    ctx.obj = AppContext(
        config_manager=ConfigManager(config_path=config_path),
        file_manager=FileManager(),
        analyzer=DataAnalyzer(),
    )


@cli.command("list-files")
@click.argument("directory", required=False, type=click.Path(path_type=Path))
@click.option(
    "--recursive/--no-recursive",
    default=False,
    show_default=True,
    help="Search for CSV files recursively.",
)
@click.pass_obj
@handle_cli_errors
def list_files(app: AppContext, directory: Path | None, recursive: bool) -> None:
    """List CSV files in a directory with basic metadata."""
    target_directory = resolve_directory(directory, app.config_manager)
    metadata = app.file_manager.list_csv_files(target_directory, recursive=recursive)

    if not metadata:
        click.echo(f"No CSV files found in '{target_directory}'.")
        return

    output_frame = pd.DataFrame(
        [
            {
                "File": item.name,
                "Rows": item.row_count,
                "Columns": item.column_count,
                "Size": app.file_manager.humanize_file_size(item.file_size_bytes),
                "Path": str(item.path),
            }
            for item in metadata
        ]
    )

    click.echo(output_frame.to_string(index=False))


@cli.command("columns")
@click.argument("file_path", type=str)
@click.option(
    "--samples",
    default=3,
    show_default=True,
    type=click.IntRange(min=1),
    help="Number of sample values to show per column.",
)
@click.pass_obj
@handle_cli_errors
def columns(app: AppContext, file_path: str, samples: int) -> None:
    """Display column names, data types, and sample values for a CSV file."""
    resolved_path = resolve_file_path(file_path, app.config_manager)
    metadata = app.file_manager.get_csv_metadata(resolved_path)
    summaries = app.analyzer.get_column_information(resolved_path, sample_size=samples)
    app.config_manager.add_recent_file(resolved_path)

    click.echo(
        f"File: {resolved_path}\nRows: {metadata.row_count}  "
        f"Columns: {metadata.column_count}  "
        f"Size: {app.file_manager.humanize_file_size(metadata.file_size_bytes)}"
    )

    if not summaries:
        click.echo("The CSV file has no columns to inspect.")
        return

    output_frame = pd.DataFrame(
        [
            {
                "Column": item.name,
                "Pandas Type": item.pandas_dtype,
                "Semantic Type": item.semantic_type,
                "Sample Values": ", ".join(item.sample_values),
            }
            for item in summaries
        ]
    )

    click.echo(output_frame.to_string(index=False))


@cli.command("plot")
@click.argument("file_path", required=False, type=str)
@click.option(
    "--chart-type",
    type=click.Choice(sorted(SUPPORTED_CHARTS), case_sensitive=False),
    default=None,
    help="Chart type to generate.",
)
@click.option("--column", default=None, help="Primary column for histogram, box, bar, or pie charts.")
@click.option("--x", default=None, help="X-axis column for line or box charts.")
@click.option("--y", default=None, help="Y-axis column for line or box charts.")
@click.option("--title", default=None, help="Custom chart title.")
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Output HTML path for the chart.",
)
@click.option(
    "--bins",
    default=None,
    type=click.IntRange(min=1),
    help="Number of bins for histogram charts. Defaults to 30.",
)
@click.option(
    "--top-n",
    default=None,
    type=click.IntRange(min=1),
    help="Maximum categories to display for bar and pie charts. Defaults to 10.",
)
@click.option("--color", default=None, help="Primary color for the chart.")
@click.option("--width", type=click.IntRange(min=1), default=None, help="Chart width in pixels.")
@click.option("--height", type=click.IntRange(min=1), default=None, help="Chart height in pixels.")
@click.option("--template", default=None, help="Plotly template name to use.")
@click.option("--save-config", "save_config_name", default=None, help="Save this chart configuration.")
@click.option("--use-config", "use_config_name", default=None, help="Load a saved chart configuration.")
@click.option(
    "--open/--no-open",
    "open_chart",
    default=None,
    help="Open the saved chart in a browser after generation.",
)
@click.pass_obj
@handle_cli_errors
def plot(
    app: AppContext,
    file_path: str | None,
    chart_type: str | None,
    column: str | None,
    x: str | None,
    y: str | None,
    title: str | None,
    output: Path | None,
    bins: int | None,
    top_n: int | None,
    color: str | None,
    width: int | None,
    height: int | None,
    template: str | None,
    save_config_name: str | None,
    use_config_name: str | None,
    open_chart: bool | None,
) -> None:
    """Generate an interactive chart for a CSV file."""
    preferences = app.config_manager.get_visualization_preferences()
    saved_config = load_saved_configuration(app.config_manager, use_config_name, expected_kind="plot")

    resolved_file_path = resolve_chart_file_path(
        file_path=file_path,
        saved_config=saved_config,
        config_manager=app.config_manager,
    )

    resolved_chart_type = resolve_chart_type(
        chart_type=chart_type,
        column=column,
        x=x,
        y=y,
        saved_config=saved_config,
        preferences=preferences,
        analyzer=app.analyzer,
        file_path=resolved_file_path,
    )

    resolved_settings = {
        "kind": "plot",
        "file_path": str(resolved_file_path),
        "chart_type": resolved_chart_type,
        "column": first_non_none(column, saved_config.get("column") if saved_config else None),
        "x": first_non_none(x, saved_config.get("x") if saved_config else None),
        "y": first_non_none(y, saved_config.get("y") if saved_config else None),
        "title": first_non_none(title, saved_config.get("title") if saved_config else None),
        "bins": first_non_none(bins, saved_config.get("bins") if saved_config else None, 30),
        "top_n": first_non_none(
            top_n,
            saved_config.get("top_n") if saved_config else None,
            10,
        ),
        "color": first_non_none(color, saved_config.get("color") if saved_config else None),
        "width": first_non_none(width, saved_config.get("width") if saved_config else None),
        "height": first_non_none(height, saved_config.get("height") if saved_config else None),
        "template": first_non_none(template, saved_config.get("template") if saved_config else None),
        "auto_open": (
            open_chart
            if open_chart is not None
            else (
                saved_config.get("auto_open")
                if saved_config and "auto_open" in saved_config
                else preferences.get("auto_open", False)
            )
        ),
    }

    dataframe = app.analyzer.load_dataframe(resolved_file_path)
    if dataframe.empty and len(dataframe.columns) == 0:
        raise click.ClickException("The selected CSV file is empty.")

    from .visualizer import Visualizer

    visualizer = Visualizer(preferences)
    figure = visualizer.create_chart(
        dataframe,
        chart_type=resolved_settings["chart_type"],
        column=resolved_settings["column"],
        x=resolved_settings["x"],
        y=resolved_settings["y"],
        title=resolved_settings["title"],
        bins=resolved_settings["bins"],
        top_n=resolved_settings["top_n"],
        color=resolved_settings["color"],
        width=resolved_settings["width"],
        height=resolved_settings["height"],
        template=resolved_settings["template"],
    )

    output_path = output or build_output_path(
        resolved_file_path, resolved_settings["chart_type"], resolved_settings["column"] or resolved_settings["y"]
    )
    saved_path = visualizer.save_figure(
        figure,
        output_path,
        auto_open=bool(resolved_settings["auto_open"]),
    )

    app.config_manager.add_recent_file(resolved_file_path)
    if save_config_name:
        app.config_manager.save_chart_configuration(save_config_name, resolved_settings)

    click.echo(f"Chart saved to: {saved_path}")


@cli.command("correlation")
@click.argument("file_path", required=False, type=str)
@click.option(
    "--columns",
    "columns_option",
    default=None,
    help="Comma-separated numeric columns to include. Defaults to all numeric columns.",
)
@click.option("--title", default=None, help="Custom heatmap title.")
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Output HTML path for the heatmap.",
)
@click.option("--width", type=click.IntRange(min=1), default=None, help="Chart width in pixels.")
@click.option("--height", type=click.IntRange(min=1), default=None, help="Chart height in pixels.")
@click.option("--template", default=None, help="Plotly template name to use.")
@click.option("--save-config", "save_config_name", default=None, help="Save this heatmap configuration.")
@click.option("--use-config", "use_config_name", default=None, help="Load a saved heatmap configuration.")
@click.option(
    "--open/--no-open",
    "open_chart",
    default=None,
    help="Open the saved chart in a browser after generation.",
)
@click.pass_obj
@handle_cli_errors
def correlation(
    app: AppContext,
    file_path: str | None,
    columns_option: str | None,
    title: str | None,
    output: Path | None,
    width: int | None,
    height: int | None,
    template: str | None,
    save_config_name: str | None,
    use_config_name: str | None,
    open_chart: bool | None,
) -> None:
    """Generate a correlation heatmap for numeric CSV columns."""
    preferences = app.config_manager.get_visualization_preferences()
    saved_config = load_saved_configuration(
        app.config_manager, use_config_name, expected_kind="correlation"
    )

    resolved_file_path = resolve_chart_file_path(
        file_path=file_path,
        saved_config=saved_config,
        config_manager=app.config_manager,
    )
    resolved_columns = first_non_none(
        split_csv_option(columns_option),
        saved_config.get("columns") if saved_config else None,
    )
    resolved_settings = {
        "kind": "correlation",
        "file_path": str(resolved_file_path),
        "columns": resolved_columns,
        "title": first_non_none(title, saved_config.get("title") if saved_config else None),
        "width": first_non_none(width, saved_config.get("width") if saved_config else None),
        "height": first_non_none(height, saved_config.get("height") if saved_config else None),
        "template": first_non_none(template, saved_config.get("template") if saved_config else None),
        "auto_open": (
            open_chart
            if open_chart is not None
            else (
                saved_config.get("auto_open")
                if saved_config and "auto_open" in saved_config
                else preferences.get("auto_open", False)
            )
        ),
    }

    dataframe = app.analyzer.load_dataframe(resolved_file_path)
    if dataframe.empty and len(dataframe.columns) == 0:
        raise click.ClickException("The selected CSV file is empty.")

    from .visualizer import Visualizer

    visualizer = Visualizer(preferences)
    figure = visualizer.create_correlation_heatmap(
        dataframe,
        columns=resolved_settings["columns"],
        title=resolved_settings["title"],
        width=resolved_settings["width"],
        height=resolved_settings["height"],
        template=resolved_settings["template"],
    )

    output_path = output or build_output_path(resolved_file_path, "correlation_heatmap")
    saved_path = visualizer.save_figure(
        figure,
        output_path,
        auto_open=bool(resolved_settings["auto_open"]),
    )

    app.config_manager.add_recent_file(resolved_file_path)
    if save_config_name:
        app.config_manager.save_chart_configuration(save_config_name, resolved_settings)

    click.echo(f"Correlation heatmap saved to: {saved_path}")


@cli.group("config")
def config_group() -> None:
    """Manage persisted CSVAgent configuration."""


@config_group.command("show")
@click.pass_obj
@handle_cli_errors
def config_show(app: AppContext) -> None:
    """Show the full JSON configuration."""
    click.echo(json.dumps(app.config_manager.get_config(), indent=2, sort_keys=True))


@config_group.command("set-default-dir")
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.pass_obj
@handle_cli_errors
def config_set_default_dir(app: AppContext, directory: Path) -> None:
    """Persist the default directory used by list-files."""
    app.config_manager.set_default_csv_directory(directory)
    click.echo(f"Default CSV directory set to: {directory.expanduser().resolve()}")


@config_group.command("set-visual")
@click.option(
    "--numeric-default",
    type=click.Choice(sorted(SUPPORTED_NUMERIC_CHARTS), case_sensitive=False),
    default=None,
    help="Default chart for numeric columns.",
)
@click.option(
    "--categorical-default",
    type=click.Choice(sorted(SUPPORTED_CATEGORICAL_CHARTS), case_sensitive=False),
    default=None,
    help="Default chart for categorical columns.",
)
@click.option(
    "--colors",
    default=None,
    help="Comma-separated plot colors, for example '#1f77b4,#ff7f0e'.",
)
@click.option("--width", type=click.IntRange(min=1), default=None, help="Default chart width.")
@click.option("--height", type=click.IntRange(min=1), default=None, help="Default chart height.")
@click.option("--template", default=None, help="Default plotly template.")
@click.option(
    "--auto-open/--no-auto-open",
    default=None,
    help="Whether new charts should open automatically after saving.",
)
@click.pass_obj
@handle_cli_errors
def config_set_visual(
    app: AppContext,
    numeric_default: str | None,
    categorical_default: str | None,
    colors: str | None,
    width: int | None,
    height: int | None,
    template: str | None,
    auto_open: bool | None,
) -> None:
    """Update persisted visualization preferences."""
    if all(
        value is None
        for value in (
            numeric_default,
            categorical_default,
            colors,
            width,
            height,
            template,
            auto_open,
        )
    ):
        raise click.ClickException("Provide at least one visualization setting to update.")

    app.config_manager.update_visualization_preferences(
        default_numeric_chart=numeric_default.lower() if numeric_default else None,
        default_categorical_chart=(
            categorical_default.lower() if categorical_default else None
        ),
        color_sequence=split_csv_option(colors),
        width=width,
        height=height,
        template=template,
        auto_open=auto_open,
    )
    click.echo("Visualization preferences updated.")


@config_group.command("recent")
@click.pass_obj
@handle_cli_errors
def config_recent(app: AppContext) -> None:
    """Show the recently inspected or visualized CSV files."""
    recent_files = app.config_manager.get_recent_files()
    if not recent_files:
        click.echo("No recently opened CSV files recorded.")
        return

    output_frame = pd.DataFrame(
        [
            {
                "Path": entry.get("path", ""),
                "Opened At (UTC)": entry.get("opened_at", ""),
            }
            for entry in recent_files
        ]
    )
    click.echo(output_frame.to_string(index=False))


@config_group.command("saved-charts")
@click.pass_obj
@handle_cli_errors
def config_saved_charts(app: AppContext) -> None:
    """List saved chart configurations."""
    saved_configs = app.config_manager.list_saved_chart_configurations()
    if not saved_configs:
        click.echo("No saved chart configurations found.")
        return

    output_frame = pd.DataFrame(
        [
            {
                "Name": name,
                "Kind": payload.get("kind", ""),
                "Chart": payload.get("chart_type", "correlation"),
                "File": payload.get("file_path", ""),
                "Saved At (UTC)": payload.get("saved_at", ""),
            }
            for name, payload in sorted(saved_configs.items())
        ]
    )
    click.echo(output_frame.to_string(index=False))


@config_group.command("show-chart")
@click.argument("name", type=str)
@click.pass_obj
@handle_cli_errors
def config_show_chart(app: AppContext, name: str) -> None:
    """Show a saved chart configuration as JSON."""
    payload = app.config_manager.get_saved_chart_configuration(name)
    click.echo(json.dumps(payload, indent=2, sort_keys=True))


@config_group.command("delete-chart")
@click.argument("name", type=str)
@click.pass_obj
@handle_cli_errors
def config_delete_chart(app: AppContext, name: str) -> None:
    """Delete a saved chart configuration."""
    app.config_manager.delete_saved_chart_configuration(name)
    click.echo(f"Deleted saved chart configuration: {name}")


def resolve_directory(directory: Path | None, config_manager: ConfigManager) -> Path:
    if directory is not None:
        resolved = directory.expanduser().resolve()
    else:
        configured_directory = config_manager.get_default_csv_directory()
        resolved = configured_directory.expanduser().resolve() if configured_directory else Path.cwd()

    if not resolved.exists():
        raise ConfigurationError(f"Directory does not exist: '{resolved}'")
    if not resolved.is_dir():
        raise ConfigurationError(f"Path is not a directory: '{resolved}'")
    return resolved


def resolve_file_path(file_path: str, config_manager: ConfigManager) -> Path:
    candidate = Path(file_path).expanduser()
    search_paths = [candidate]

    if not candidate.is_absolute():
        search_paths.append(Path.cwd() / candidate)
        default_directory = config_manager.get_default_csv_directory()
        if default_directory is not None:
            search_paths.append(default_directory / candidate)

    for path in search_paths:
        if path.exists() and path.is_file():
            return path.resolve()

    searched = ", ".join(str(path) for path in search_paths)
    raise ConfigurationError(f"Could not locate CSV file '{file_path}'. Searched: {searched}")


def resolve_chart_file_path(
    *,
    file_path: str | None,
    saved_config: dict[str, Any] | None,
    config_manager: ConfigManager,
) -> Path:
    resolved_input = file_path or (saved_config.get("file_path") if saved_config else None)
    if not resolved_input:
        raise ConfigurationError(
            "A CSV file path is required unless the saved configuration includes one."
        )
    return resolve_file_path(str(resolved_input), config_manager)


def resolve_chart_type(
    *,
    chart_type: str | None,
    column: str | None,
    x: str | None,
    y: str | None,
    saved_config: dict[str, Any] | None,
    preferences: dict[str, Any],
    analyzer: DataAnalyzer,
    file_path: Path,
) -> str:
    if chart_type is not None:
        return chart_type.lower()

    if saved_config and saved_config.get("chart_type"):
        return str(saved_config["chart_type"]).lower()

    if x or y:
        raise ConfigurationError(
            "When using --x or --y, specify --chart-type explicitly or use a saved configuration."
        )

    target_column = column
    if not target_column:
        raise ConfigurationError(
            "Provide --chart-type, or provide --column so CSVAgent can use your default chart preference."
        )

    dataframe = analyzer.load_dataframe(file_path, usecols=[target_column])
    analyzer.ensure_columns_exist(dataframe, [target_column])
    semantic_type = analyzer.get_semantic_type(dataframe[target_column])

    if semantic_type == "numeric":
        return str(preferences.get("default_numeric_chart", "histogram")).lower()
    return str(preferences.get("default_categorical_chart", "bar")).lower()


def load_saved_configuration(
    config_manager: ConfigManager,
    config_name: str | None,
    *,
    expected_kind: str,
) -> dict[str, Any] | None:
    if config_name is None:
        return None

    payload = config_manager.get_saved_chart_configuration(config_name)
    actual_kind = payload.get("kind")
    if actual_kind != expected_kind:
        raise ConfigurationError(
            f"Saved chart configuration '{config_name}' is '{actual_kind}', "
            f"expected '{expected_kind}'."
        )
    return payload


def split_csv_option(value: str | None) -> list[str] | None:
    if value is None:
        return None
    parts = [item.strip() for item in value.split(",")]
    filtered = [item for item in parts if item]
    return filtered or None


def first_non_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def build_output_path(
    file_path: Path, chart_type: str, column_name: str | None = None
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = sanitize_name(column_name) if column_name else chart_type
    file_name = f"{file_path.stem}_{sanitize_name(chart_type)}_{suffix}_{timestamp}.html"
    return Path.cwd() / "charts" / file_name


def sanitize_name(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in value).strip("_") or "chart"
