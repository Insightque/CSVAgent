"""Flask web UI for CSVAgent."""

from __future__ import annotations

import json
import math
import re
from numbers import Number
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.io as pio
from flask import Flask, Response, jsonify, render_template, request

from csvagent.config_manager import ConfigManager
from csvagent.csv_reader import read_csv_with_fallbacks
from csvagent.data_analyzer import DataAnalyzer
from csvagent.exceptions import CSVAgentError, FileAnalysisError, VisualizationError
from csvagent.file_manager import CSVFileMetadata, FileManager
from csvagent.visualizer import Visualizer

app = Flask(__name__)

config_manager = ConfigManager()
file_manager = FileManager()
analyzer = DataAnalyzer()

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 250
SUPPORTED_WEB_CHARTS = {"bar", "histogram", "line", "scatter"}


@app.get("/")
def index() -> str:
    """Render the single-page UI."""
    return render_template("index.html", initial_state=build_initial_state())


@app.post("/api/folder/select")
def select_folder() -> Response:
    """Persist the selected folder and return its CSV files."""
    payload = request.get_json(silent=True) or {}
    directory = resolve_directory(payload.get("folder_path", ""))
    config_manager.set_default_csv_directory(directory)
    return jsonify(build_folder_response(directory))


@app.post("/api/folder/browse")
def browse_folder() -> Response:
    """Show a helpful message when environment-native picker is unavailable.

    Browser environments cannot safely expose an absolute local directory path,
    so we keep this endpoint as a clear fallback to manual folder selection.
    """
    return jsonify(
        {
            "error": "디렉터리 브라우저는 현재 환경에서 비활성화되어 있습니다. 폴더 경로를 직접 입력한 뒤 'Load Folder'를 눌러주세요.",
            "fallback": True,
        }
    ), 400


@app.post("/api/files/load")
def load_file() -> Response:
    """Load CSV metadata and the first page of rows."""
    payload = request.get_json(silent=True) or {}
    file_path = resolve_csv_file(payload.get("file_path", ""))
    page_size = sanitize_page_size(payload.get("page_size"))
    file_payload = build_file_payload(file_path, page=1, page_size=page_size)

    config_manager.add_recent_file(file_path)
    config_manager.add_web_open_file(file_path)

    web_ui_state = config_manager.get_web_ui_state()
    return jsonify(
        {
            "file": file_payload,
            "graph_configuration": web_ui_state.get("graph_configurations", {}).get(
                str(file_path)
            ),
        }
    )


@app.get("/api/files/table")
def get_table_page() -> Response:
    """Return one page of CSV rows."""
    file_path = resolve_csv_file(request.args.get("file_path", ""))
    page = sanitize_page_number(request.args.get("page"))
    page_size = sanitize_page_size(request.args.get("page_size"))
    return jsonify(build_table_page_payload(file_path, page=page, page_size=page_size))


@app.post("/api/files/close")
def close_file() -> Response:
    """Remove a file from the persisted open-table layout."""
    payload = request.get_json(silent=True) or {}
    file_path = normalize_path_reference(payload.get("file_path", ""))
    config_manager.remove_web_open_file(file_path)
    return jsonify({"status": "ok", "file_path": str(file_path)})


@app.post("/api/graphs/generate")
def generate_graph() -> Response:
    """Generate a Plotly figure for a CSV file and persist its configuration."""
    payload = request.get_json(silent=True) or {}
    file_path = resolve_csv_file(payload.get("file_path", ""))
    graph_configuration = parse_graph_configuration(payload)
    figure = create_figure(file_path, graph_configuration)

    config_manager.set_web_graph_configuration(file_path, graph_configuration)

    return jsonify(
        {
            "figure": json.loads(figure.to_json()),
            "graph_configuration": graph_configuration,
        }
    )


@app.post("/api/graphs/export-html")
def export_graph_html() -> Response:
    """Generate a downloadable HTML document for the current graph."""
    payload = request.get_json(silent=True) or {}
    file_path = resolve_csv_file(payload.get("file_path", ""))
    graph_configuration = parse_graph_configuration(payload)
    figure = create_figure(file_path, graph_configuration)

    config_manager.set_web_graph_configuration(file_path, graph_configuration)

    html = pio.to_html(figure, full_html=True, include_plotlyjs="cdn")
    filename = build_chart_filename(file_path, graph_configuration)
    return Response(
        html,
        mimetype="text/html",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.errorhandler(CSVAgentError)
def handle_csvagent_error(error: CSVAgentError) -> tuple[Response, int] | tuple[str, int]:
    """Return JSON errors for API routes."""
    if request.path.startswith("/api/"):
        return jsonify({"error": str(error)}), 400
    return str(error), 400


@app.errorhandler(ValueError)
def handle_value_error(error: ValueError) -> tuple[Response, int] | tuple[str, int]:
    """Return JSON errors for bad request values."""
    if request.path.startswith("/api/"):
        return jsonify({"error": str(error)}), 400
    return str(error), 400


def build_initial_state() -> dict[str, Any]:
    """Build the state used to bootstrap the SPA."""
    selected_directory = config_manager.get_default_csv_directory()
    available_files: list[dict[str, Any]] = []

    if selected_directory and selected_directory.exists() and selected_directory.is_dir():
        try:
            available_files = list_directory_csv_files(selected_directory)
        except CSVAgentError:
            available_files = []

    web_ui_state = config_manager.get_web_ui_state()
    open_files = [
        path
        for path in web_ui_state.get("open_files", [])
        if Path(path).expanduser().is_file()
    ]

    return {
        "selected_folder": str(selected_directory) if selected_directory else "",
        "files": available_files,
        "open_files": open_files,
        "graph_configurations": web_ui_state.get("graph_configurations", {}),
        "default_page_size": DEFAULT_PAGE_SIZE,
    }


def build_folder_response(directory: Path) -> dict[str, Any]:
    """Serialize the folder selection response."""
    return {
        "folder_path": str(directory),
        "files": list_directory_csv_files(directory),
    }


def list_directory_csv_files(directory: Path) -> list[dict[str, Any]]:
    """Serialize all CSV metadata for a directory."""
    return [
        serialize_metadata(metadata)
        for metadata in file_manager.list_csv_files(directory, recursive=False)
    ]


def build_file_payload(file_path: Path, page: int, page_size: int) -> dict[str, Any]:
    """Return metadata, headers, and the requested table page for one CSV file."""
    metadata = file_manager.get_csv_metadata(file_path)
    table_page = build_table_page_payload(
        file_path,
        page=page,
        page_size=page_size,
        metadata=metadata,
    )
    return {
        "name": metadata.name,
        "path": str(metadata.path),
        "metadata": serialize_metadata(metadata),
        "table": table_page,
    }


def build_table_page_payload(
    file_path: Path,
    *,
    page: int,
    page_size: int,
    metadata: CSVFileMetadata | None = None,
) -> dict[str, Any]:
    """Read a single page of CSV rows."""
    csv_metadata = metadata or file_manager.get_csv_metadata(file_path)
    total_rows = csv_metadata.row_count
    total_pages = max(1, math.ceil(total_rows / page_size)) if total_rows else 1
    current_page = min(max(1, page), total_pages)
    page_frame = read_csv_page(file_path, page=current_page, page_size=page_size)

    return {
        "columns": list(page_frame.columns),
        "rows": dataframe_to_records(page_frame),
        "page": current_page,
        "page_size": page_size,
        "total_rows": total_rows,
        "total_pages": total_pages,
    }


def read_csv_page(file_path: Path, *, page: int, page_size: int) -> pd.DataFrame:
    """Read a small page of data while preserving the CSV header."""
    start_row = max(0, (page - 1) * page_size)
    skiprows = range(1, start_row + 1) if start_row else None
    try:
        return read_csv_with_fallbacks(
            file_path,
            low_memory=False,
            nrows=page_size,
            skiprows=skiprows,
        )
    except pd.errors.EmptyDataError:
        return read_csv_with_fallbacks(file_path, nrows=0)


def dataframe_to_records(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame into JSON-safe records."""
    sanitized = dataframe.copy().astype(object)
    sanitized = sanitized.where(pd.notna(sanitized), None)
    records = sanitized.to_dict(orient="records")
    return [
        {column: serialize_cell(value) for column, value in row.items()}
        for row in records
    ]


def serialize_cell(value: Any) -> Any:
    """Normalize DataFrame cell values for JSON transport."""
    if value is None:
        return None
    if isinstance(value, (bool, Number, str)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def serialize_metadata(metadata: CSVFileMetadata) -> dict[str, Any]:
    """Convert file metadata into a JSON-friendly structure."""
    return {
        "name": metadata.name,
        "path": str(metadata.path),
        "row_count": metadata.row_count,
        "column_count": metadata.column_count,
        "file_size_bytes": metadata.file_size_bytes,
        "file_size_human": file_manager.humanize_file_size(metadata.file_size_bytes),
    }


def parse_graph_configuration(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize graph settings received from the browser."""
    chart_type = str(payload.get("chart_type", "")).strip().lower()
    if chart_type not in SUPPORTED_WEB_CHARTS:
        raise VisualizationError(
            "Unsupported chart type. Choose line, bar, scatter, or histogram."
        )

    x_column = normalize_optional_text(payload.get("x_column"))
    y_column = normalize_optional_text(payload.get("y_column"))

    if chart_type == "histogram":
        if x_column is None and y_column is None:
            raise VisualizationError("Histogram charts require an X-axis column.")
    else:
        if x_column is None or y_column is None:
            raise VisualizationError(
                f"{chart_type.title()} charts require both X-axis and Y-axis columns."
            )

    return {
        "chart_type": chart_type,
        "x_column": x_column,
        "y_column": y_column,
    }


def create_figure(file_path: Path, graph_configuration: dict[str, Any]) -> Any:
    """Create a plotly figure using the configured CSVAgent visualizer."""
    dataframe = analyzer.load_dataframe(file_path)
    visualizer = Visualizer(config_manager.get_visualization_preferences())

    chart_type = graph_configuration["chart_type"]
    x_column = graph_configuration.get("x_column")
    y_column = graph_configuration.get("y_column")

    title = f"{file_path.name} · {chart_type.title()} chart"

    if chart_type == "histogram":
        target_column = x_column or y_column
        if target_column is None:
            raise VisualizationError("Histogram charts require an X-axis column.")
        return visualizer.create_chart(
            dataframe,
            chart_type="histogram",
            column=target_column,
            title=title,
        )

    return visualizer.create_chart(
        dataframe,
        chart_type=chart_type,
        x=x_column,
        y=y_column,
        title=title,
    )


# Removed Tk-based directory picker integration because it is not stable in the
# Flask debug server environment.


def resolve_directory(raw_path: str) -> Path:
    """Resolve and validate a directory path."""
    if not str(raw_path).strip():
        raise FileAnalysisError("Select a folder before listing CSV files.")

    directory = Path(str(raw_path).strip()).expanduser().resolve()
    if not directory.exists():
        raise FileAnalysisError(f"Directory does not exist: '{directory}'")
    if not directory.is_dir():
        raise FileAnalysisError(f"Path is not a directory: '{directory}'")
    return directory


def resolve_csv_file(raw_path: str) -> Path:
    """Resolve and validate a CSV file path."""
    file_path = normalize_path_reference(raw_path)
    if not file_path.exists():
        raise FileAnalysisError(f"CSV file does not exist: '{file_path}'")
    if not file_path.is_file():
        raise FileAnalysisError(f"Path is not a file: '{file_path}'")
    if file_path.suffix.lower() != ".csv":
        raise FileAnalysisError(f"Path is not a CSV file: '{file_path}'")
    return file_path


def normalize_path_reference(raw_path: str) -> Path:
    """Resolve a path string without requiring the target to exist."""
    if not str(raw_path).strip():
        raise FileAnalysisError("Select a CSV file before loading data.")
    return Path(str(raw_path).strip()).expanduser().resolve()


def sanitize_page_number(raw_page: Any) -> int:
    """Clamp incoming page numbers to a positive integer."""
    try:
        page = int(raw_page)
    except (TypeError, ValueError):
        page = 1
    return max(1, page)


def sanitize_page_size(raw_page_size: Any) -> int:
    """Clamp incoming page size values."""
    try:
        page_size = int(raw_page_size)
    except (TypeError, ValueError):
        page_size = DEFAULT_PAGE_SIZE
    return min(MAX_PAGE_SIZE, max(1, page_size))


def normalize_optional_text(value: Any) -> str | None:
    """Return trimmed strings or None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_chart_filename(file_path: Path, graph_configuration: dict[str, Any]) -> str:
    """Create a readable download filename for exported charts."""
    filename_bits = [
        file_path.stem,
        graph_configuration["chart_type"],
        graph_configuration.get("x_column") or "",
        graph_configuration.get("y_column") or "",
    ]
    filename = "-".join(bit for bit in filename_bits if bit)
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", filename).strip("-")
    return f"{normalized or 'csvagent-chart'}.html"


if __name__ == "__main__":
    app.run(debug=True)
