"""Shared CSV reading helpers with encoding fallbacks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from pandas.errors import EmptyDataError, ParserError

from .exceptions import FileAnalysisError

ENCODING_CANDIDATES = ("utf-8", "utf-8-sig", "latin-1")


def read_csv_with_fallbacks(file_path: Path, **kwargs: Any) -> Any:
    """Read a CSV file with a small set of encoding fallbacks."""
    errors: list[str] = []

    for encoding in ENCODING_CANDIDATES:
        try:
            return pd.read_csv(file_path, encoding=encoding, **kwargs)
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
        except EmptyDataError:
            raise
        except ParserError as exc:
            raise FileAnalysisError(
                f"Failed to parse CSV file '{file_path}': {exc}"
            ) from exc
        except FileNotFoundError as exc:
            raise FileAnalysisError(f"CSV file not found: '{file_path}'") from exc
        except OSError as exc:
            raise FileAnalysisError(f"Unable to read CSV file '{file_path}': {exc}") from exc

    joined_errors = "; ".join(errors) or "unknown encoding error"
    raise FileAnalysisError(
        f"Could not decode CSV file '{file_path}' using supported encodings. "
        f"Attempts: {joined_errors}"
    )
