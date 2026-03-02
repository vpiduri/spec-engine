"""Tests for spec_engine/scanner/django.py — DjangoScanner."""

import pytest
from pathlib import Path

from spec_engine.scanner.django import DjangoScanner, _convert_django_path
from spec_engine.config import Config

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "django"


def make_scanner(path: Path) -> DjangoScanner:
    return DjangoScanner(str(path), Config())


class TestHelpers:
    def test_convert_django_path_typed(self):
        assert _convert_django_path("accounts/<str:account_id>/") == "/accounts/{account_id}/"

    def test_convert_django_path_untyped(self):
        assert _convert_django_path("items/<item_id>/") == "/items/{item_id}/"

    def test_convert_django_path_int_converter(self):
        assert _convert_django_path("posts/<int:pk>/") == "/posts/{pk}/"

    def test_convert_adds_leading_slash(self):
        result = _convert_django_path("accounts/")
        assert result.startswith("/")


class TestDjangoScanner:
    @pytest.fixture
    def routes(self):
        scanner = make_scanner(FIXTURE_DIR.parent.parent)
        all_routes = scanner.scan()
        return [r for r in all_routes if "fixtures/django" in r.file or "fixtures\\django" in r.file]

    def test_finds_routes(self, routes):
        assert len(routes) >= 6  # 6 CRUD + 1 action + 2 APIView methods

    def test_has_list_route(self, routes):
        list_routes = [r for r in routes if r.method == "GET" and "{pk}" not in r.path and "{account_id}" not in r.path]
        assert len(list_routes) >= 1

    def test_has_create_route(self, routes):
        post_routes = [r for r in routes if r.method == "POST" and "{pk}" not in r.path]
        assert len(post_routes) >= 1

    def test_has_retrieve_route(self, routes):
        get_pk = [r for r in routes if r.method == "GET" and "{pk}" in r.path]
        assert len(get_pk) >= 1

    def test_has_update_route(self, routes):
        put_routes = [r for r in routes if r.method == "PUT"]
        assert len(put_routes) >= 1

    def test_has_partial_update_route(self, routes):
        patch_routes = [r for r in routes if r.method == "PATCH"]
        assert len(patch_routes) >= 1

    def test_has_destroy_route(self, routes):
        delete_routes = [r for r in routes if r.method == "DELETE"]
        assert len(delete_routes) >= 1

    def test_has_action_route(self, routes):
        action_routes = [r for r in routes if "activate" in r.path]
        assert len(action_routes) >= 1
        assert action_routes[0].method == "POST"

    def test_apiview_get_route(self, routes):
        apiview_gets = [r for r in routes if r.method == "GET" and "account_id" in r.path]
        assert len(apiview_gets) >= 1

    def test_framework_is_django(self, routes):
        for r in routes:
            assert r.framework == "django"


class TestDjangoViewSetRoutes:
    def test_viewset_generates_six_routes(self, tmp_path):
        views = tmp_path / "views.py"
        views.write_text("""
from rest_framework import viewsets

class ProductViewSet(viewsets.ModelViewSet):
    queryset = None
""")
        urls = tmp_path / "urls.py"
        urls.write_text("""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'products', views.ProductViewSet, basename='product')

urlpatterns = [path('', include(router.urls))]
""")
        scanner = DjangoScanner(str(tmp_path), Config())
        routes = scanner.scan()
        assert len(routes) == 6
        methods = [r.method for r in routes]
        assert "GET" in methods
        assert "POST" in methods
        assert "PUT" in methods
        assert "PATCH" in methods
        assert "DELETE" in methods

    def test_action_adds_extra_route(self, tmp_path):
        views = tmp_path / "views.py"
        views.write_text("""
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

class ProductViewSet(viewsets.ModelViewSet):
    queryset = None

    @action(detail=True, methods=['post'], url_path='publish')
    def publish(self, request, pk=None):
        return Response({'status': 'published'})
""")
        urls = tmp_path / "urls.py"
        urls.write_text("""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'products', views.ProductViewSet, basename='product')
urlpatterns = [path('', include(router.urls))]
""")
        scanner = DjangoScanner(str(tmp_path), Config())
        routes = scanner.scan()
        publish_routes = [r for r in routes if "publish" in r.path]
        assert len(publish_routes) == 1
        assert publish_routes[0].method == "POST"


class TestDjangoMixinViewSets:
    def test_readonly_viewset_generates_only_list_and_retrieve(self, tmp_path):
        views = tmp_path / "views.py"
        views.write_text("""
from rest_framework import viewsets

class BookViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = None
""")
        urls = tmp_path / "urls.py"
        urls.write_text("""
from rest_framework.routers import DefaultRouter
from . import views
router = DefaultRouter()
router.register(r'books', views.BookViewSet, basename='book')
urlpatterns = []
""")
        scanner = DjangoScanner(str(tmp_path), Config())
        routes = scanner.scan()
        assert len(routes) == 2
        methods = {r.method for r in routes}
        assert methods == {"GET"}
        actions = {r.handler.split(".")[-1] for r in routes}
        assert "list" in actions
        assert "retrieve" in actions

    def test_mixin_list_create_generates_two_routes(self, tmp_path):
        views = tmp_path / "views.py"
        views.write_text("""
from rest_framework import mixins, viewsets

class OrderViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = None
""")
        urls = tmp_path / "urls.py"
        urls.write_text("""
from rest_framework.routers import DefaultRouter
from . import views
router = DefaultRouter()
router.register(r'orders', views.OrderViewSet, basename='order')
urlpatterns = []
""")
        scanner = DjangoScanner(str(tmp_path), Config())
        routes = scanner.scan()
        assert len(routes) == 2
        actions = {r.handler.split(".")[-1] for r in routes}
        assert "list" in actions
        assert "create" in actions

    def test_mixin_retrieve_update_generates_three_routes(self, tmp_path):
        views = tmp_path / "views.py"
        views.write_text("""
from rest_framework import mixins, viewsets

class ItemViewSet(mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = None
""")
        urls = tmp_path / "urls.py"
        urls.write_text("""
from rest_framework.routers import DefaultRouter
from . import views
router = DefaultRouter()
router.register(r'items', views.ItemViewSet, basename='item')
urlpatterns = []
""")
        scanner = DjangoScanner(str(tmp_path), Config())
        routes = scanner.scan()
        # RetrieveModelMixin → retrieve; UpdateModelMixin → update + partial_update
        assert len(routes) == 3
        actions = {r.handler.split(".")[-1] for r in routes}
        assert "retrieve" in actions
        assert "update" in actions
        assert "partial_update" in actions

    def test_generic_viewset_no_standard_routes_only_action(self, tmp_path):
        views = tmp_path / "views.py"
        views.write_text("""
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

class ToolViewSet(viewsets.GenericViewSet):
    queryset = None

    @action(detail=False, methods=['post'], url_path='run')
    def run(self, request):
        return Response({'result': 'ok'})
""")
        urls = tmp_path / "urls.py"
        urls.write_text("""
from rest_framework.routers import DefaultRouter
from . import views
router = DefaultRouter()
router.register(r'tools', views.ToolViewSet, basename='tool')
urlpatterns = []
""")
        scanner = DjangoScanner(str(tmp_path), Config())
        routes = scanner.scan()
        # GenericViewSet has no standard routes; only the @action route
        assert len(routes) == 1
        assert "run" in routes[0].path
        assert routes[0].method == "POST"
