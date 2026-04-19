"""CSV file discovery and metadata collection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from pandas.errors import EmptyDataError, ParserError

from .csv_reader import ENCODING_CANDIDATES
from .exceptions import FileAnalysisError


@dataclass(slots=True)
class CSVFileMetadata:
    """Metadata for a discovered CSV file."""

    name: str
    path: Path
    row_count: int
    column_count: int
    file_size_bytes: int


class FileManager:
    """Manage CSV discovery and metadata inspection."""

    def list_csv_files(self, directory: Path, recursive: bool = False) -> list[CSVFileMetadata]:
        directory = directory.expanduser().resolve()
        if not directory.exists():
            raise FileAnalysisError(f"Directory does not exist: '{directory}'")
        if not directory.is_dir():
            raise FileAnalysisError(f"Path is not a directory: '{directory}'")

        csv_paths = sorted(
            (
                path
                for path in (directory.rglob("*") if recursive else directory.iterdir())
                if path.is_file() and path.suffix.lower() == ".csv"
            ),
            key=lambda path: path.name.lower(),
        )

        return [self.get_csv_metadata(path) for path in csv_paths]

    def get_csv_metadata(self, file_path: Path) -> CSVFileMetadata:
        file_path = file_path.expanduser().resolve()
        if not file_path.exists():
            raise FileAnalysisError(f"CSV file does not exist: '{file_path}'")
        if not file_path.is_file():
            raise FileAnalysisError(f"Path is not a file: '{file_path}'")

        encoding, column_count = self._probe_csv(file_path)
        row_count = self._count_rows(file_path, encoding)
        file_size_bytes = file_path.stat().st_size

        return CSVFileMetadata(
            name=file_path.name,
            path=file_path,
            row_count=row_count,
            column_count=column_count,
            file_size_bytes=file_size_bytes,
        )

    def _probe_csv(self, file_path: Path) -> tuple[str, int]:
        errors: list[str] = []

        for encoding in ENCODING_CANDIDATES:
            try:
                header_frame = pd.read_csv(file_path, encoding=encoding, nrows=0)
                return encoding, len(header_frame.columns)
            except UnicodeDecodeError as exc:
                errors.append(f"{encoding}: {exc}")
            except EmptyDataError:
                return encoding, 0
            except ParserError as exc:
                raise FileAnalysisError(
                    f"Failed to parse CSV header for '{file_path}': {exc}"
                ) from exc
            except FileAnalysisError:
                raise
            except Exception as exc:  # pragma: no cover - defensive boundary
                raise FileAnalysisError(
                    f"Unable to inspect CSV file '{file_path}': {exc}"
                ) from exc

        joined_errors = "; ".join(errors) or "unknown encoding error"
        raise FileAnalysisError(
            f"Unable to inspect CSV header for '{file_path}'. Attempts: {joined_errors}"
        )

    def _count_rows(self, file_path: Path, encoding: str, chunksize: int = 50000) -> int:
        try:
            reader = pd.read_csv(
                file_path,
                encoding=encoding,
                chunksize=chunksize,
                low_memory=False,
            )
            return sum(len(chunk) for chunk in reader)
        except EmptyDataError:
            return 0
        except ParserError as exc:
            raise FileAnalysisError(
                f"Failed to count rows for '{file_path}': {exc}"
            ) from exc
        except OSError as exc:
            raise FileAnalysisError(f"Unable to read '{file_path}': {exc}") from exc

    @staticmethod
    def humanize_file_size(size_bytes: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size_bytes)
        for unit in units:
            if size < 1024 or unit == units[-1]:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size_bytes} B"
