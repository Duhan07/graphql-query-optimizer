"""Tests for utility functions."""

import pytest
from gql_optimizer.utils import (
    camel_to_snake,
    snake_to_camel,
    GraphQLLibrary,
    detect_graphql_library,
    generate_cache_key,
    validate_model,
    merge_fields,
)


class TestCamelToSnake:
    """Test camel_to_snake function."""
    
    def test_simple_camel_case(self):
        assert camel_to_snake("createdAt") == "created_at"
    
    def test_pascal_case(self):
        assert camel_to_snake("CreatedAt") == "created_at"
    
    def test_multiple_words(self):
        assert camel_to_snake("orderItemDetails") == "order_item_details"
    
    def test_with_acronym(self):
        assert camel_to_snake("XMLParser") == "xml_parser"
        assert camel_to_snake("userID") == "user_id"
    
    def test_already_snake_case(self):
        assert camel_to_snake("already_snake") == "already_snake"
    
    def test_single_word(self):
        assert camel_to_snake("word") == "word"
        assert camel_to_snake("Word") == "word"
    
    def test_with_numbers(self):
        assert camel_to_snake("item2Price") == "item2_price"


class TestSnakeToCamel:
    """Test snake_to_camel function."""
    
    def test_simple_snake_case(self):
        assert snake_to_camel("created_at") == "createdAt"
    
    def test_multiple_words(self):
        assert snake_to_camel("order_item_details") == "orderItemDetails"
    
    def test_already_camel_case(self):
        assert snake_to_camel("alreadyCamel") == "alreadyCamel"
    
    def test_single_word(self):
        assert snake_to_camel("word") == "word"


class TestDetectGraphQLLibrary:
    """Test detect_graphql_library function."""
    
    def test_none_info(self):
        result = detect_graphql_library(None)
        assert result == GraphQLLibrary.UNKNOWN
    
    def test_strawberry_by_module(self):
        class MockInfo:
            pass
        
        MockInfo.__module__ = "strawberry.types.info"
        info = MockInfo()
        
        result = detect_graphql_library(info)
        assert result == GraphQLLibrary.STRAWBERRY
    
    def test_graphene_by_module(self):
        class MockInfo:
            pass
        
        MockInfo.__module__ = "graphene.types.info"
        info = MockInfo()
        
        result = detect_graphql_library(info)
        assert result == GraphQLLibrary.GRAPHENE
    
    def test_strawberry_by_attribute(self):
        class MockInfo:
            selected_fields = []
        
        MockInfo.__module__ = "unknown"
        info = MockInfo()
        
        result = detect_graphql_library(info)
        assert result == GraphQLLibrary.STRAWBERRY
    
    def test_graphene_by_attribute(self):
        class MockInfo:
            field_nodes = []
        
        MockInfo.__module__ = "unknown"
        info = MockInfo()
        
        result = detect_graphql_library(info)
        assert result == GraphQLLibrary.GRAPHENE


class TestGenerateCacheKey:
    """Test generate_cache_key function."""
    
    def test_generates_string(self):
        class MockModel:
            __tablename__ = "orders"
        
        key = generate_cache_key(MockModel, {"id", "name"}, None, 10, 0)
        
        assert isinstance(key, str)
        assert len(key) == 32  # MD5 hash length
    
    def test_same_params_same_key(self):
        class MockModel:
            __tablename__ = "orders"
        
        key1 = generate_cache_key(MockModel, {"id", "name"}, None, 10, 0)
        key2 = generate_cache_key(MockModel, {"id", "name"}, None, 10, 0)
        
        assert key1 == key2
    
    def test_different_fields_different_key(self):
        class MockModel:
            __tablename__ = "orders"
        
        key1 = generate_cache_key(MockModel, {"id", "name"}, None, 10, 0)
        key2 = generate_cache_key(MockModel, {"id", "status"}, None, 10, 0)
        
        assert key1 != key2
    
    def test_different_limit_different_key(self):
        class MockModel:
            __tablename__ = "orders"
        
        key1 = generate_cache_key(MockModel, {"id"}, None, 10, 0)
        key2 = generate_cache_key(MockModel, {"id"}, None, 20, 0)
        
        assert key1 != key2


class TestValidateModel:
    """Test validate_model function."""
    
    def test_valid_model(self):
        class ValidModel:
            __table__ = object()
            __tablename__ = "test"
        
        assert validate_model(ValidModel) is True
    
    def test_invalid_model_no_table(self):
        class InvalidModel:
            __tablename__ = "test"
        
        assert validate_model(InvalidModel) is False
    
    def test_invalid_model_no_tablename(self):
        class InvalidModel:
            __table__ = object()
        
        assert validate_model(InvalidModel) is False
    
    def test_invalid_model_plain_class(self):
        class PlainClass:
            pass
        
        assert validate_model(PlainClass) is False


class TestMergeFields:
    """Test merge_fields function."""
    
    def test_merge_basic(self):
        requested = {"name", "status"}
        always = {"id"}
        columns = {"id", "name", "status", "created_at"}
        
        result = merge_fields(requested, always, columns)
        
        assert result == {"id", "name", "status"}
    
    def test_filters_invalid_fields(self):
        requested = {"name", "invalid_field"}
        always = {"id"}
        columns = {"id", "name", "status"}
        
        result = merge_fields(requested, always, columns)
        
        assert "invalid_field" not in result
        assert result == {"id", "name"}
    
    def test_always_include_overrides(self):
        requested = {"name"}
        always = {"id", "created_at"}
        columns = {"id", "name", "created_at"}
        
        result = merge_fields(requested, always, columns)
        
        assert "id" in result
        assert "created_at" in result
    
    def test_empty_requested(self):
        requested = set()
        always = {"id"}
        columns = {"id", "name"}
        
        result = merge_fields(requested, always, columns)
        
        assert result == {"id"}
