# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2024-12-31

### Added
- Initial release
- `QueryOptimizer` class for field selection optimization
- `QueryCache` with TTL and LRU eviction support
- `SyncDataLoader` for synchronous batch loading
- `AsyncDataLoader` for asynchronous batch loading
- Support for Strawberry GraphQL
- Support for Graphene GraphQL
- Support for Ariadne GraphQL
- Full async/await support
- Comprehensive type hints
- Thread-safe cache implementation
- Nested field extraction
- Model relationship detection

### Features
- Field selection optimization (only query requested columns)
- Query caching with configurable TTL
- DataLoader pattern for N+1 problem prevention
- Automatic GraphQL library detection
- camelCase to snake_case conversion
- Custom cache key generation
- Cache invalidation by model
- Cache statistics tracking

## [0.1.0] - 2024-12-01

### Added
- Initial development version
- Basic QueryOptimizer implementation
- Simple caching mechanism
