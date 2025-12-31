"""
Field extraction from GraphQL info objects.

Handles extraction of requested fields from different
GraphQL libraries (Strawberry, Graphene, Ariadne).
"""

from typing import Any, Dict, Set, Type, Optional
from collections import defaultdict
import logging

from .utils import (
    GraphQLLibrary,
    detect_graphql_library,
    camel_to_snake,
    get_model_relationships,
    get_model_columns
)

logger = logging.getLogger(__name__)


class FieldExtractor:
    """
    Extract requested fields from GraphQL info object.
    
    Supports:
        - Strawberry
        - Graphene
        - Ariadne
    
    Usage:
        >>> extractor = FieldExtractor(info, OrderModel)
        >>> fields = extractor.extract()
        >>> # {'id', 'order_id', 'status', 'total_price'}
        
        >>> # With nested fields
        >>> all_fields = extractor.extract_with_nested()
        >>> # {'Orders': {'id', 'courier_id'}, 'Pm_Users': {'id', 'name'}}
    """
    
    def __init__(
        self,
        info: Any,
        model: Type,
        library: Optional[GraphQLLibrary] = None
    ):
        """
        Initialize extractor.
        
        Args:
            info: GraphQL resolver info object
            model: SQLAlchemy model class
            library: GraphQL library (auto-detected if not provided)
        """
        self.info = info
        self.model = model
        self.library = library or detect_graphql_library(info)
        self._model_columns = get_model_columns(model)
    
    def extract(self) -> Set[str]:
        """
        Extract flat list of requested fields.
        
        Returns:
            Set of field names (snake_case)
        """
        if self.library == GraphQLLibrary.STRAWBERRY:
            return self._extract_strawberry()
        elif self.library == GraphQLLibrary.GRAPHENE:
            return self._extract_graphene()
        elif self.library == GraphQLLibrary.ARIADNE:
            return self._extract_ariadne()
        else:
            # Fallback: return all model columns
            logger.warning(
                f"Unknown GraphQL library, returning all columns for {self.model.__tablename__}"
            )
            return self._model_columns.copy()
    
    def extract_with_nested(self) -> Dict[str, Set[str]]:
        """
        Extract fields including nested/related fields.
        
        Returns:
            Dictionary mapping table name to set of fields
            
        Example:
            >>> {
            >>>     'Orders': {'id', 'order_id', 'courier_id'},
            >>>     'Pm_Users': {'id', 'name', 'phone'}
            >>> }
        """
        result = defaultdict(set)
        relationships = get_model_relationships(self.model)
        
        if self.library == GraphQLLibrary.STRAWBERRY:
            self._extract_nested_strawberry(result, relationships)
        elif self.library in (GraphQLLibrary.GRAPHENE, GraphQLLibrary.ARIADNE):
            self._extract_nested_graphene(result, relationships)
        else:
            result[self.model.__tablename__] = self._model_columns.copy()
        
        return dict(result)
    
    # ==================== STRAWBERRY ====================
    
    def _extract_strawberry(self) -> Set[str]:
        """Extract fields from Strawberry info."""
        fields = set()
        
        try:
            selected_fields = self.info.selected_fields
            
            if selected_fields:
                for field in selected_fields:
                    if hasattr(field, 'selections') and field.selections:
                        for selection in field.selections:
                            field_name = selection.name
                            if not field_name.startswith('__'):
                                fields.add(camel_to_snake(field_name))
        except Exception as e:
            logger.warning(f"Strawberry field extraction error: {e}")
            return self._model_columns.copy()
        
        return fields
    
    def _extract_nested_strawberry(
        self,
        result: Dict[str, Set[str]],
        relationships: Dict[str, Type],
        selections: Any = None,
        current_model: Type = None
    ) -> None:
        """Recursively extract fields from Strawberry including nested."""
        if current_model is None:
            current_model = self.model
        
        try:
            if selections is None:
                selected_fields = self.info.selected_fields
                if selected_fields:
                    for field in selected_fields:
                        if hasattr(field, 'selections') and field.selections:
                            self._process_strawberry_selections(
                                field.selections,
                                result,
                                relationships,
                                current_model
                            )
        except Exception as e:
            logger.warning(f"Nested field extraction error: {e}")
    
    def _process_strawberry_selections(
        self,
        selections: Any,
        result: Dict[str, Set[str]],
        relationships: Dict[str, Type],
        current_model: Type
    ) -> None:
        """Process Strawberry selections recursively."""
        table_name = current_model.__tablename__
        
        for selection in selections:
            field_name = selection.name
            if field_name.startswith('__'):
                continue
            
            snake_name = camel_to_snake(field_name)
            
            # Check if it's a relationship
            if snake_name in relationships:
                related_model = relationships[snake_name]
                
                # Add foreign key to current model
                fk_name = f"{snake_name}_id"
                if hasattr(current_model, fk_name):
                    result[table_name].add(fk_name)
                
                # Process nested selections
                if hasattr(selection, 'selections') and selection.selections:
                    nested_relationships = get_model_relationships(related_model)
                    self._process_strawberry_selections(
                        selection.selections,
                        result,
                        nested_relationships,
                        related_model
                    )
            else:
                result[table_name].add(snake_name)
    
    # ==================== GRAPHENE ====================
    
    def _extract_graphene(self) -> Set[str]:
        """Extract fields from Graphene/Ariadne info."""
        fields = set()
        
        try:
            field_nodes = (
                getattr(self.info, 'field_nodes', None) or
                getattr(self.info, 'field_asts', None) or
                []
            )
            
            for field_node in field_nodes:
                selection_set = getattr(field_node, 'selection_set', None)
                if selection_set and hasattr(selection_set, 'selections'):
                    for selection in selection_set.selections:
                        if hasattr(selection, 'name'):
                            field_name = selection.name.value
                            if not field_name.startswith('__'):
                                fields.add(camel_to_snake(field_name))
        except Exception as e:
            logger.warning(f"Graphene field extraction error: {e}")
            return self._model_columns.copy()
        
        return fields
    
    def _extract_ariadne(self) -> Set[str]:
        """Extract fields from Ariadne info (same as Graphene)."""
        return self._extract_graphene()
    
    def _extract_nested_graphene(
        self,
        result: Dict[str, Set[str]],
        relationships: Dict[str, Type]
    ) -> None:
        """Extract nested fields from Graphene/Ariadne."""
        try:
            field_nodes = (
                getattr(self.info, 'field_nodes', None) or
                getattr(self.info, 'field_asts', None) or
                []
            )
            
            for field_node in field_nodes:
                selection_set = getattr(field_node, 'selection_set', None)
                if selection_set and hasattr(selection_set, 'selections'):
                    self._process_graphene_selections(
                        selection_set.selections,
                        result,
                        relationships,
                        self.model
                    )
        except Exception as e:
            logger.warning(f"Nested field extraction error: {e}")
    
    def _process_graphene_selections(
        self,
        selections: Any,
        result: Dict[str, Set[str]],
        relationships: Dict[str, Type],
        current_model: Type
    ) -> None:
        """Process Graphene selections recursively."""
        table_name = current_model.__tablename__
        
        for selection in selections:
            if not hasattr(selection, 'name'):
                continue
            
            field_name = selection.name.value
            if field_name.startswith('__'):
                continue
            
            snake_name = camel_to_snake(field_name)
            
            # Check if it's a relationship
            if snake_name in relationships:
                related_model = relationships[snake_name]
                
                # Add foreign key
                fk_name = f"{snake_name}_id"
                if hasattr(current_model, fk_name):
                    result[table_name].add(fk_name)
                
                # Process nested
                nested_selection_set = getattr(selection, 'selection_set', None)
                if nested_selection_set and hasattr(nested_selection_set, 'selections'):
                    nested_relationships = get_model_relationships(related_model)
                    self._process_graphene_selections(
                        nested_selection_set.selections,
                        result,
                        nested_relationships,
                        related_model
                    )
            else:
                result[table_name].add(snake_name)


def extract_fields(
    info: Any,
    model: Type,
    include_nested: bool = False
) -> Set[str]:
    """
    Convenience function to extract fields from info.
    
    Args:
        info: GraphQL resolver info object
        model: SQLAlchemy model class
        include_nested: Whether to include nested relationship fields
        
    Returns:
        Set of field names
    """
    extractor = FieldExtractor(info, model)
    
    if include_nested:
        nested = extractor.extract_with_nested()
        return nested.get(model.__tablename__, set())
    
    return extractor.extract()
