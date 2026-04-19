"""Custom exception types for CSVAgent."""


class CSVAgentError(Exception):
    """Base exception for CSVAgent."""


class ConfigurationError(CSVAgentError):
    """Raised when configuration cannot be loaded or saved."""


class FileAnalysisError(CSVAgentError):
    """Raised when a CSV file cannot be read or analyzed."""


class VisualizationError(CSVAgentError):
    """Raised when a chart cannot be generated."""
