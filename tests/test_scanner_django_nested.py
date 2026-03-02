"""Tests for DRF nested router support in spec_engine/scanner/django.py."""

from pathlib import Path

import pytest

from spec_engine.scanner.django import DjangoScanner
from spec_engine.config import Config


def _make_scanner(tmp_path: Path) -> DjangoScanner:
    return DjangoScanner(str(tmp_path), Config())


def _write_urls(tmp_path: Path, content: str) -> Path:
    f = tmp_path / "urls.py"
    f.write_text(content)
    return f


def _write_views(tmp_path: Path, viewsets: list[str]) -> Path:
    """Write a views.py with ModelViewSet subclasses."""
    lines = ["from rest_framework.viewsets import ModelViewSet\n"]
    for name in viewsets:
        lines.append(
            f"class {name}(ModelViewSet):\n"
            f"    pass\n\n"
        )
    f = tmp_path / "views.py"
    f.write_text("".join(lines))
    return f


NESTED_URLS = """\
from rest_framework.routers import DefaultRouter
from rest_framework_nested.routers import NestedSimpleRouter
from .views import AccountViewSet, TransactionViewSet

router = DefaultRouter()
router.register(r'accounts', AccountViewSet, basename='account')

nested = NestedSimpleRouter(router, r'accounts', lookup='account')
nested.register(r'transactions', TransactionViewSet, basename='account-transaction')
"""

NESTED_URLS_NO_LOOKUP = """\
from rest_framework.routers import DefaultRouter
from rest_framework_nested.routers import NestedSimpleRouter
from .views import AccountViewSet, TransactionViewSet

router = DefaultRouter()
router.register(r'accounts', AccountViewSet, basename='account')

nested = NestedSimpleRouter(router, r'accounts')
nested.register(r'transactions', TransactionViewSet)
"""

NESTED_URLS_CUSTOM_LOOKUP = """\
from rest_framework.routers import DefaultRouter
from rest_framework_nested.routers import NestedSimpleRouter
from .views import OrderViewSet, ItemViewSet

router = DefaultRouter()
router.register(r'orders', OrderViewSet, basename='order')

sub = NestedSimpleRouter(router, r'orders', lookup='order')
sub.register(r'items', ItemViewSet)
"""

SIMPLE_URLS = """\
from rest_framework.routers import DefaultRouter
from .views import ProductViewSet

router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')
"""


class TestDjangoNestedRouters:
    def test_nested_router_produces_compound_path(self, tmp_path):
        _write_urls(tmp_path, NESTED_URLS)
        _write_views(tmp_path, ["AccountViewSet", "TransactionViewSet"])
        scanner = _make_scanner(tmp_path)
        routes = scanner.scan()
        paths = [r.path for r in routes]
        # Should have routes like /accounts/{account_pk}/transactions/ and .../transactions/{pk}
        nested_paths = [p for p in paths if "account_pk" in p]
        assert len(nested_paths) >= 1, f"No nested paths found. Paths: {paths}"

    def test_default_lookup_field_is_pk(self, tmp_path):
        _write_urls(tmp_path, NESTED_URLS_NO_LOOKUP)
        _write_views(tmp_path, ["AccountViewSet", "TransactionViewSet"])
        scanner = _make_scanner(tmp_path)
        routes = scanner.scan()
        paths = [r.path for r in routes]
        # No lookup kwarg → lookup="pk" → lookup_field="pk_pk"
        nested_paths = [p for p in paths if "pk_pk" in p]
        assert len(nested_paths) >= 1, f"Expected pk_pk in paths. Paths: {paths}"

    def test_custom_lookup_kwarg(self, tmp_path):
        _write_urls(tmp_path, NESTED_URLS_CUSTOM_LOOKUP)
        _write_views(tmp_path, ["OrderViewSet", "ItemViewSet"])
        scanner = _make_scanner(tmp_path)
        routes = scanner.scan()
        paths = [r.path for r in routes]
        nested_paths = [p for p in paths if "order_pk" in p]
        assert len(nested_paths) >= 1, f"Expected order_pk in paths. Paths: {paths}"

    def test_nested_crud_routes_count(self, tmp_path):
        _write_urls(tmp_path, NESTED_URLS)
        _write_views(tmp_path, ["AccountViewSet", "TransactionViewSet"])
        scanner = _make_scanner(tmp_path)
        routes = scanner.scan()
        nested = [r for r in routes if "account_pk" in r.path]
        # ModelViewSet gives 6 CRUD routes under nested path
        assert len(nested) == 6, f"Expected 6 nested routes, got {len(nested)}. Paths: {[r.path for r in nested]}"

    def test_simple_router_routes_unaffected(self, tmp_path):
        _write_urls(tmp_path, SIMPLE_URLS)
        _write_views(tmp_path, ["ProductViewSet"])
        scanner = _make_scanner(tmp_path)
        routes = scanner.scan()
        # All routes should start with /products, none with nested lookup params
        paths = [r.path for r in routes]
        assert all(p.startswith("/products") for p in paths), f"Unexpected paths: {paths}"
        assert not any("pk" in p and "products" not in p for p in paths)
