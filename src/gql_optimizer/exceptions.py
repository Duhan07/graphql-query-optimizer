"""
Custom exceptions for GraphQL Query Optimizer.
"""


class GQLOptimizerError(Exception):
    """Base exception for all optimizer errors."""
    pass


class SessionNotFoundError(GQLOptimizerError):
    """Raised when database session cannot be found."""
    
    def __init__(self, message: str = "Database session not found. Please provide a session."):
        self.message = message
        super().__init__(self.message)


class InvalidModelError(GQLOptimizerError):
    """Raised when an invalid SQLAlchemy model is provided."""
    
    def __init__(self, model_type: str = "unknown"):
        self.message = f"Invalid SQLAlchemy model: {model_type}. Must be a mapped class."
        super().__init__(self.message)


class FieldExtractionError(GQLOptimizerError):
    """Raised when field extraction from GraphQL info fails."""
    
    def __init__(self, library: str, details: str = ""):
        self.message = f"Failed to extract fields from {library} info object. {details}"
        super().__init__(self.message)


class CacheError(GQLOptimizerError):
    """Raised when cache operations fail."""
    pass


class DataLoaderError(GQLOptimizerError):
    """Raised when DataLoader operations fail."""
    pass


class UnsupportedLibraryError(GQLOptimizerError):
    """Raised when an unsupported GraphQL library is detected."""
    
    def __init__(self, library: str = "unknown"):
        self.message = f"Unsupported GraphQL library: {library}. Supported: Strawberry, Graphene, Ariadne"
        super().__init__(self.message)
