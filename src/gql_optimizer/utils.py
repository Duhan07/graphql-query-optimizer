"""
Utility functions for GraphQL Query Optimizer.
"""

import re
import hashlib
import json
from enum import Enum, auto
from typing import Any, Dict, Set, Type, Optional


class GraphQLLibrary(Enum):
    """Supported GraphQL libraries."""
    STRAWBERRY = auto()
    GRAPHENE = auto()
    ARIADNE = auto()
    UNKNOWN = auto()


def camel_to_snake(name: str) -> str:
    """
    Convert camelCase or PascalCase to snake_case.
    
    Args:
        name: String in camelCase or PascalCase
        
    Returns:
        String in snake_case
        
    Examples:
        >>> camel_to_snake("createdAt")
        'created_at'
        >>> camel_to_snake("OrderID")
        'order_id'
        >>> camel_to_snake("XMLParser")
        'xml_parser'
    """
    # Handle acronyms and regular camelCase
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def snake_to_camel(name: str) -> str:
    """
    Convert snake_case to camelCase.
    
    Args:
        name: String in snake_case
        
    Returns:
        String in camelCase
        
    Examples:
        >>> snake_to_camel("created_at")
        'createdAt'
        >>> snake_to_camel("order_id")
        'orderId'
    """
    components = name.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])


def detect_graphql_library(info: Any) -> GraphQLLibrary:
    """
    Detect which GraphQL library is being used from the info object.
    
    Args:
        info: GraphQL resolver info object
        
    Returns:
        GraphQLLibrary enum value
    """
    if info is None:
        return GraphQLLibrary.UNKNOWN
    
    info_module = type(info).__module__
    
    # Check module name
    if 'strawberry' in info_module:
        return GraphQLLibrary.STRAWBERRY
    elif 'graphene' in info_module or 'graphql' in info_module:
        return GraphQLLibrary.GRAPHENE
    elif 'ariadne' in info_module:
        return GraphQLLibrary.ARIADNE
    
    # Check for specific attributes
    if hasattr(info, 'selected_fields'):
        return GraphQLLibrary.STRAWBERRY
    elif hasattr(info, 'field_asts') or hasattr(info, 'field_nodes'):
        return GraphQLLibrary.GRAPHENE
    
    return GraphQLLibrary.UNKNOWN


def generate_cache_key(
    model: Type,
    fields: Set[str],
    filters: Optional[Dict] = None,
    limit: int = 10,
    offset: int = 0,
    extra: Optional[str] = None
) -> str:
    """
    Generate a unique cache key from query parameters.
    
    Args:
        model: SQLAlchemy model class
        fields: Set of field names being queried
        filters: Dictionary of filter conditions
        limit: Query limit
        offset: Query offset
        extra: Additional string to include in key
        
    Returns:
        MD5 hash string as cache key
    """
    key_data = {
        "model": getattr(model, '__tablename__', str(model)),
        "fields": sorted(list(fields)),
        "filters": str(sorted(filters.items())) if filters else "",
        "limit": limit,
        "offset": offset,
        "extra": extra or ""
    }
    key_str = json.dumps(key_data, sort_keys=True)
    return hashlib.md5(key_str.encode()).hexdigest()


def get_model_columns(model: Type) -> Set[str]:
    """
    Get all column names from a SQLAlchemy model.
    
    Args:
        model: SQLAlchemy model class
        
    Returns:
        Set of column names
    """
    if hasattr(model, '__table__'):
        return {col.key for col in model.__table__.columns}
    return set()


def get_model_relationships(model: Type) -> Dict[str, Type]:
    """
    Get all relationships from a SQLAlchemy model.
    
    Args:
        model: SQLAlchemy model class
        
    Returns:
        Dictionary mapping relationship name to related model class
    """
    try:
        from sqlalchemy.inspection import inspect
        
        relationships = {}
        mapper = inspect(model)
        
        for rel in mapper.relationships:
            relationships[rel.key] = rel.mapper.class_
        
        return relationships
    except Exception:
        return {}


def validate_model(model: Type) -> bool:
    """
    Validate that the provided class is a valid SQLAlchemy model.
    
    Args:
        model: Class to validate
        
    Returns:
        True if valid SQLAlchemy model
    """
    return hasattr(model, '__table__') and hasattr(model, '__tablename__')


def merge_fields(
    requested: Set[str],
    always_include: Set[str],
    model_columns: Set[str]
) -> Set[str]:
    """
    Merge requested fields with required fields, filtered by model columns.
    
    Args:
        requested: Fields requested in GraphQL query
        always_include: Fields that must always be included
        model_columns: Valid column names from the model
        
    Returns:
        Set of valid fields to query
    """
    return (requested & model_columns) | (always_include & model_columns)
