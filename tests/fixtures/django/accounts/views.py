from rest_framework import viewsets, views, status
from rest_framework.decorators import action
from rest_framework.response import Response


class AccountViewSet(viewsets.ModelViewSet):
    queryset = None
    serializer_class = None

    @action(detail=True, methods=['post'], url_path='activate')
    def activate(self, request, pk=None):
        return Response({'status': 'activated'})


class AccountDetailView(views.APIView):
    def get(self, request, account_id):
        return Response({})

    def put(self, request, account_id):
        return Response({})
