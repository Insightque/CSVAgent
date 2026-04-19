"""Configuration persistence for CSVAgent."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .exceptions import ConfigurationError

DEFAULT_CONFIG: dict[str, Any] = {
    "default_csv_directory": None,
    "preferred_visualization": {
        "default_numeric_chart": "histogram",
        "default_categorical_chart": "bar",
        "color_sequence": [
            "#1f77b4",
            "#ff7f0e",
            "#2ca02c",
            "#d62728",
            "#17becf",
        ],
        "width": 1000,
        "height": 600,
        "template": "plotly_white",
        "auto_open": False,
    },
    "recent_files": [],
    "saved_chart_configurations": {},
    "web_ui": {
        "open_files": [],
        "graph_configurations": {},
    },
}


class ConfigManager:
    """Load, validate, and persist JSON configuration."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = self._resolve_config_path(config_path)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config = self._load_or_initialize()

    def _resolve_config_path(self, config_path: Path | None) -> Path:
        env_path = os.getenv("CSVAGENT_CONFIG_PATH")
        raw_path = config_path or (Path(env_path).expanduser() if env_path else None)
        if raw_path is not None:
            return raw_path.expanduser()

        preferred_path = Path.home() / ".csvagent" / "config.json"
        if self._is_parent_writable(preferred_path):
            return preferred_path

        return Path.cwd() / ".csvagent" / "config.json"

    def _is_parent_writable(self, path: Path) -> bool:
        probe = path.expanduser().parent
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        return os.access(probe, os.W_OK)

    def _load_or_initialize(self) -> dict[str, Any]:
        if not self.config_path.exists():
            config = copy.deepcopy(DEFAULT_CONFIG)
            self._write(config)
            return config

        try:
            with self.config_path.open("r", encoding="utf-8") as file_handle:
                raw_content = file_handle.read()

            if not raw_content.strip():
                config = copy.deepcopy(DEFAULT_CONFIG)
                self._write(config)
                return config

            loaded = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise ConfigurationError(
                f"Configuration file '{self.config_path}' is not valid JSON: {exc}"
            ) from exc
        except OSError as exc:
            raise ConfigurationError(
                f"Unable to read configuration file '{self.config_path}': {exc}"
            ) from exc

        merged = self._deep_merge(copy.deepcopy(DEFAULT_CONFIG), loaded)
        merged["recent_files"] = self._normalize_recent_files(merged.get("recent_files", []))
        merged["saved_chart_configurations"] = dict(
            merged.get("saved_chart_configurations", {})
        )
        merged["web_ui"] = self._normalize_web_ui_state(merged.get("web_ui", {}))
        if merged != loaded:
            self._write(merged)
        return merged

    def _deep_merge(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                base[key] = self._deep_merge(base[key], value)
            else:
                base[key] = value
        return base

    def _normalize_recent_files(self, recent_files: list[Any]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []

        for entry in recent_files:
            if isinstance(entry, str):
                normalized.append({"path": entry, "opened_at": ""})
            elif isinstance(entry, dict) and "path" in entry:
                normalized.append(
                    {
                        "path": str(entry["path"]),
                        "opened_at": str(entry.get("opened_at", "")),
                    }
                )

        return normalized[:10]

    def _write(self, config: dict[str, Any]) -> None:
        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.config_path.parent,
                delete=False,
                prefix=f"{self.config_path.stem}.",
                suffix=".tmp",
            ) as file_handle:
                json.dump(config, file_handle, indent=2, sort_keys=True)
                file_handle.flush()
                os.fsync(file_handle.fileno())
                temp_path = file_handle.name

            os.replace(temp_path, self.config_path)
        except OSError as exc:
            raise ConfigurationError(
                f"Unable to write configuration file '{self.config_path}': {exc}"
            ) from exc
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    def _normalize_web_ui_state(self, web_ui: Any) -> dict[str, Any]:
        if not isinstance(web_ui, dict):
            return copy.deepcopy(DEFAULT_CONFIG["web_ui"])

        open_files = []
        for entry in web_ui.get("open_files", []):
            if isinstance(entry, str) and entry.strip():
                open_files.append(entry)

        graph_configurations: dict[str, dict[str, Any]] = {}
        raw_graphs = web_ui.get("graph_configurations", {})
        if isinstance(raw_graphs, dict):
            for path, configuration in raw_graphs.items():
                if isinstance(path, str) and path.strip() and isinstance(configuration, dict):
                    graph_configurations[path] = copy.deepcopy(configuration)

        return {
            "open_files": open_files,
            "graph_configurations": graph_configurations,
        }

    def save(self) -> None:
        self._write(self._config)

    def get_config(self) -> dict[str, Any]:
        return copy.deepcopy(self._config)

    def get_default_csv_directory(self) -> Path | None:
        configured_path = self._config.get("default_csv_directory")
        if not configured_path:
            return None
        return Path(configured_path).expanduser()

    def set_default_csv_directory(self, directory: Path) -> None:
        directory = directory.expanduser().resolve()
        if not directory.exists():
            raise ConfigurationError(f"Directory does not exist: '{directory}'")
        if not directory.is_dir():
            raise ConfigurationError(f"Path is not a directory: '{directory}'")

        self._config["default_csv_directory"] = str(directory)
        self.save()

    def get_visualization_preferences(self) -> dict[str, Any]:
        return copy.deepcopy(self._config["preferred_visualization"])

    def update_visualization_preferences(
        self,
        *,
        default_numeric_chart: str | None = None,
        default_categorical_chart: str | None = None,
        color_sequence: list[str] | None = None,
        width: int | None = None,
        height: int | None = None,
        template: str | None = None,
        auto_open: bool | None = None,
    ) -> None:
        visualization = self._config["preferred_visualization"]

        if default_numeric_chart is not None:
            visualization["default_numeric_chart"] = default_numeric_chart
        if default_categorical_chart is not None:
            visualization["default_categorical_chart"] = default_categorical_chart
        if color_sequence is not None:
            visualization["color_sequence"] = color_sequence
        if width is not None:
            if width <= 0:
                raise ConfigurationError("Visualization width must be a positive integer.")
            visualization["width"] = width
        if height is not None:
            if height <= 0:
                raise ConfigurationError("Visualization height must be a positive integer.")
            visualization["height"] = height
        if template is not None:
            visualization["template"] = template
        if auto_open is not None:
            visualization["auto_open"] = auto_open

        self.save()

    def add_recent_file(self, file_path: Path, limit: int = 10) -> None:
        normalized_path = str(file_path.expanduser().resolve())
        timestamp = datetime.now(timezone.utc).isoformat()
        current_entries = [
            entry
            for entry in self._config.get("recent_files", [])
            if entry.get("path") != normalized_path
        ]
        current_entries.insert(0, {"path": normalized_path, "opened_at": timestamp})
        self._config["recent_files"] = current_entries[:limit]
        self.save()

    def get_recent_files(self) -> list[dict[str, str]]:
        return copy.deepcopy(self._config.get("recent_files", []))

    def get_web_ui_state(self) -> dict[str, Any]:
        return copy.deepcopy(self._config.get("web_ui", DEFAULT_CONFIG["web_ui"]))

    def set_web_open_files(self, file_paths: list[Path | str]) -> None:
        unique_paths: list[str] = []
        for file_path in file_paths:
            normalized_path = str(Path(file_path).expanduser().resolve())
            if normalized_path not in unique_paths:
                unique_paths.append(normalized_path)

        self._config["web_ui"]["open_files"] = unique_paths
        self.save()

    def add_web_open_file(self, file_path: Path | str) -> None:
        normalized_path = str(Path(file_path).expanduser().resolve())
        open_files = [
            path
            for path in self._config["web_ui"].get("open_files", [])
            if path != normalized_path
        ]
        open_files.append(normalized_path)
        self._config["web_ui"]["open_files"] = open_files
        self.save()

    def remove_web_open_file(self, file_path: Path | str) -> None:
        normalized_path = str(Path(file_path).expanduser().resolve())
        open_files = [
            path
            for path in self._config["web_ui"].get("open_files", [])
            if path != normalized_path
        ]
        self._config["web_ui"]["open_files"] = open_files
        self.save()

    def set_web_graph_configuration(
        self, file_path: Path | str, configuration: dict[str, Any] | None
    ) -> None:
        normalized_path = str(Path(file_path).expanduser().resolve())
        graph_configurations = self._config["web_ui"].setdefault(
            "graph_configurations", {}
        )

        if configuration is None:
            graph_configurations.pop(normalized_path, None)
        else:
            graph_configurations[normalized_path] = copy.deepcopy(configuration)

        self.save()

    def save_chart_configuration(self, name: str, chart_config: dict[str, Any]) -> None:
        if not name.strip():
            raise ConfigurationError("Saved chart configuration name cannot be empty.")

        saved_configs = self._config["saved_chart_configurations"]
        payload = copy.deepcopy(chart_config)
        payload["saved_at"] = datetime.now(timezone.utc).isoformat()
        saved_configs[name] = payload
        self.save()

    def list_saved_chart_configurations(self) -> dict[str, dict[str, Any]]:
        return copy.deepcopy(self._config.get("saved_chart_configurations", {}))

    def get_saved_chart_configuration(self, name: str) -> dict[str, Any]:
        saved_configs = self._config.get("saved_chart_configurations", {})
        if name not in saved_configs:
            raise ConfigurationError(f"No saved chart configuration named '{name}'.")
        return copy.deepcopy(saved_configs[name])

    def delete_saved_chart_configuration(self, name: str) -> None:
        saved_configs = self._config.get("saved_chart_configurations", {})
        if name not in saved_configs:
            raise ConfigurationError(f"No saved chart configuration named '{name}'.")
        del saved_configs[name]
        self.save()
