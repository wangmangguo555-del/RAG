class RagError(Exception):
    """Base class for expected application errors."""

    code = "RAG_ERROR"
    retryable = False


class ConfigurationError(RagError):
    code = "CONFIGURATION_ERROR"


class RepositoryNotFoundError(RagError):
    code = "REPOSITORY_NOT_FOUND"


class InvalidRepositoryError(RagError):
    code = "INVALID_REPOSITORY"


class IndexingError(RagError):
    code = "INDEXING_ERROR"


class ModelUnavailableError(RagError):
    code = "MODEL_UNAVAILABLE"
    retryable = True


class VectorStoreUnavailableError(RagError):
    code = "VECTOR_STORE_UNAVAILABLE"
    retryable = True


class IndexConsistencyError(RagError):
    code = "INDEX_CONSISTENCY_ERROR"
    retryable = True


class SourceUnavailableError(RagError):
    code = "SOURCE_UNAVAILABLE"
    retryable = True


class NoPublishedSnapshotError(RagError):
    code = "NO_PUBLISHED_SNAPSHOT"
