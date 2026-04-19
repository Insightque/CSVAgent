"""Plotly chart generation for CSVAgent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
from pandas.api.types import is_numeric_dtype
from plotly.graph_objs import Figure

from .exceptions import VisualizationError


class Visualizer:
    """Build and save plotly figures."""

    def __init__(self, preferences: dict[str, Any]) -> None:
        self.preferences = preferences

    def create_chart(
        self,
        dataframe: pd.DataFrame,
        *,
        chart_type: str,
        column: str | None = None,
        x: str | None = None,
        y: str | None = None,
        title: str | None = None,
        bins: int = 30,
        top_n: int = 10,
        color: str | None = None,
        width: int | None = None,
        height: int | None = None,
        template: str | None = None,
    ) -> Figure:
        chart_type = chart_type.lower()

        if chart_type == "histogram":
            target_column = column or x or y
            if not target_column:
                raise VisualizationError("Histogram charts require a numeric column.")
            self._ensure_numeric_column(dataframe, target_column)
            figure = px.histogram(
                dataframe,
                x=target_column,
                nbins=bins,
                title=title or f"Histogram of {target_column}",
                color_discrete_sequence=self._get_color_sequence(color),
            )
        elif chart_type == "scatter":
            if x is None or y is None:
                raise VisualizationError("Scatter charts require both X and Y columns.")
            self._ensure_columns_exist(dataframe, [x, y])
            figure = px.scatter(
                dataframe,
                x=x,
                y=y,
                title=title or f"Scatter Plot of {y} vs {x}",
                color_discrete_sequence=self._get_color_sequence(color),
            )
        elif chart_type == "line":
            target_y = y or column
            if not target_y:
                raise VisualizationError("Line charts require a numeric Y column.")
            self._ensure_numeric_column(dataframe, target_y)

            if x is None:
                plot_frame = dataframe.copy()
                plot_frame.insert(0, "row_number", range(1, len(plot_frame) + 1))
                x = "row_number"
            else:
                plot_frame = dataframe

            figure = px.line(
                plot_frame,
                x=x,
                y=target_y,
                title=title or f"Line Plot of {target_y}",
            )
            figure.update_traces(line={"color": self._get_color_sequence(color)[0]})
        elif chart_type == "box":
            target_y = y or column
            if not target_y:
                raise VisualizationError("Box plots require a numeric column.")
            self._ensure_numeric_column(dataframe, target_y)
            figure = px.box(
                dataframe,
                x=x,
                y=target_y,
                title=title or f"Box Plot of {target_y}",
                color_discrete_sequence=self._get_color_sequence(color),
            )
        elif chart_type == "bar":
            if x is not None and y is not None:
                self._ensure_columns_exist(dataframe, [x, y])
                figure = px.bar(
                    dataframe,
                    x=x,
                    y=y,
                    title=title or f"Bar Chart of {y} by {x}",
                    color_discrete_sequence=self._get_color_sequence(color),
                )
            else:
                target_column = column or x
                if not target_column:
                    raise VisualizationError("Bar charts require either X and Y columns or a categorical column.")
                count_frame = self._build_count_frame(dataframe, target_column, top_n=top_n)
                figure = px.bar(
                    count_frame,
                    x=target_column,
                    y="count",
                    title=title or f"Category Counts for {target_column}",
                    color_discrete_sequence=self._get_color_sequence(color),
                )
        elif chart_type == "pie":
            target_column = column or x
            if not target_column:
                raise VisualizationError("Pie charts require a categorical column.")
            count_frame = self._build_count_frame(dataframe, target_column, top_n=top_n)
            figure = px.pie(
                count_frame,
                names=target_column,
                values="count",
                title=title or f"Distribution of {target_column}",
                color_discrete_sequence=self._get_color_sequence(color),
            )
        else:
            raise VisualizationError(
                f"Unsupported chart type '{chart_type}'. "
                "Supported types: histogram, line, scatter, box, bar, pie."
            )

        self._apply_layout(figure, width=width, height=height, template=template)
        return figure

    def create_correlation_heatmap(
        self,
        dataframe: pd.DataFrame,
        *,
        columns: list[str] | None = None,
        title: str | None = None,
        width: int | None = None,
        height: int | None = None,
        template: str | None = None,
    ) -> Figure:
        if columns is not None:
            missing = [column for column in columns if column not in dataframe.columns]
            if missing:
                raise VisualizationError(
                    f"Column(s) not found for heatmap: {', '.join(missing)}"
                )
            numeric_frame = dataframe[columns].select_dtypes(include="number")
        else:
            numeric_frame = dataframe.select_dtypes(include="number")

        if numeric_frame.shape[1] < 2:
            raise VisualizationError(
                "Correlation heatmaps require at least two numeric columns."
            )

        correlation = numeric_frame.corr(numeric_only=True)
        figure = px.imshow(
            correlation,
            text_auto=".2f",
            aspect="auto",
            color_continuous_scale="RdBu",
            zmin=-1,
            zmax=1,
            title=title or "Correlation Heatmap",
        )
        self._apply_layout(figure, width=width, height=height, template=template)
        return figure

    def save_figure(self, figure: Figure, output_path: Path, auto_open: bool = False) -> Path:
        output_path = output_path.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            figure.write_html(
                str(output_path),
                full_html=True,
                include_plotlyjs="cdn",
                auto_open=auto_open,
            )
        except OSError as exc:
            raise VisualizationError(
                f"Unable to save chart to '{output_path}': {exc}"
            ) from exc
        return output_path

    def _apply_layout(
        self,
        figure: Figure,
        *,
        width: int | None,
        height: int | None,
        template: str | None,
    ) -> None:
        figure.update_layout(
            template=template or self.preferences.get("template", "plotly_white"),
            width=width or self.preferences.get("width", 1000),
            height=height or self.preferences.get("height", 600),
            margin={"l": 40, "r": 40, "t": 80, "b": 40},
        )

    def _build_count_frame(
        self, dataframe: pd.DataFrame, column: str, top_n: int
    ) -> pd.DataFrame:
        self._ensure_columns_exist(dataframe, [column])

        counts = dataframe[column].fillna("<missing>").astype(str).value_counts()
        if counts.empty:
            raise VisualizationError(f"Column '{column}' does not contain any plottable values.")

        if top_n > 0 and len(counts) > top_n:
            top_counts = counts.head(top_n).copy()
            remainder = int(counts.iloc[top_n:].sum())
            if remainder > 0:
                top_counts.loc["Other"] = remainder
            counts = top_counts

        return counts.rename_axis(column).reset_index(name="count")

    def _ensure_numeric_column(self, dataframe: pd.DataFrame, column: str) -> None:
        self._ensure_columns_exist(dataframe, [column])
        if not is_numeric_dtype(dataframe[column]):
            raise VisualizationError(f"Column '{column}' is not numeric.")

    def _ensure_columns_exist(self, dataframe: pd.DataFrame, columns: list[str]) -> None:
        missing = [column for column in columns if column not in dataframe.columns]
        if missing:
            raise VisualizationError(
                f"Column(s) not found in the CSV file: {', '.join(missing)}"
            )

    def _get_color_sequence(self, override_color: str | None) -> list[str]:
        configured = list(self.preferences.get("color_sequence", []))
        if override_color is None:
            return configured or ["#1f77b4"]

        deduplicated = [value for value in configured if value != override_color]
        return [override_color, *deduplicated] if deduplicated else [override_color]
