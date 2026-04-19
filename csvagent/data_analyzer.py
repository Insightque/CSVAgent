"""Column inspection and DataFrame loading utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_numeric_dtype,
)
from pandas.errors import EmptyDataError

from .csv_reader import read_csv_with_fallbacks
from .exceptions import FileAnalysisError


@dataclass(slots=True)
class ColumnSummary:
    """Summary information for a CSV column."""

    name: str
    pandas_dtype: str
    semantic_type: str
    sample_values: list[str]


class DataAnalyzer:
    """Analyze CSV columns and load data for visualization."""

    def load_dataframe(self, file_path: Path, usecols: list[str] | None = None) -> pd.DataFrame:
        file_path = file_path.expanduser().resolve()
        if not file_path.exists():
            raise FileAnalysisError(f"CSV file does not exist: '{file_path}'")

        try:
            return read_csv_with_fallbacks(file_path, low_memory=False, usecols=usecols)
        except EmptyDataError:
            return pd.DataFrame()

    def get_column_information(
        self, file_path: Path, sample_size: int = 3
    ) -> list[ColumnSummary]:
        if sample_size <= 0:
            raise FileAnalysisError("Sample size must be greater than zero.")

        dataframe = self.load_dataframe(file_path)
        if dataframe.empty and len(dataframe.columns) == 0:
            return []

        summaries: list[ColumnSummary] = []
        for column_name in dataframe.columns:
            series = dataframe[column_name]
            summaries.append(
                ColumnSummary(
                    name=column_name,
                    pandas_dtype=str(series.dtype),
                    semantic_type=self.get_semantic_type(series),
                    sample_values=self.get_sample_values(series, sample_size),
                )
            )
        return summaries

    def ensure_columns_exist(self, dataframe: pd.DataFrame, columns: list[str]) -> None:
        missing = [column for column in columns if column not in dataframe.columns]
        if missing:
            missing_display = ", ".join(missing)
            raise FileAnalysisError(f"Column(s) not found in CSV: {missing_display}")

    def get_numeric_columns(self, dataframe: pd.DataFrame) -> list[str]:
        return [
            column
            for column in dataframe.columns
            if is_numeric_dtype(dataframe[column])
        ]

    def get_sample_values(self, series: pd.Series, sample_size: int) -> list[str]:
        if len(series) == 0:
            return ["<no rows>"]

        unique_values: list[str] = []
        for value in series.dropna().astype(str):
            if value not in unique_values:
                unique_values.append(value)
            if len(unique_values) >= sample_size:
                break

        if not unique_values:
            return ["<missing values only>"]
        return unique_values

    def get_semantic_type(self, series: pd.Series) -> str:
        if is_numeric_dtype(series):
            return "numeric"
        if is_datetime64_any_dtype(series):
            return "datetime"
        if is_bool_dtype(series):
            return "boolean"
        return "categorical"
