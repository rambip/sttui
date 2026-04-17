"""Application-level errors."""


class SttuiError(Exception):
    """Base error for concise user-facing failures."""


class ConfigError(SttuiError):
    """Configuration is missing or invalid."""


class RecordingError(SttuiError):
    """Audio recording failed."""


class TranscriptionError(SttuiError):
    """Transcription API call or parsing failed."""


class RetryableTranscriptionError(TranscriptionError):
    """Transcription failed due to network issues or formatting problems and can be retried."""


class ClipboardError(SttuiError):
    """Clipboard operation failed."""
