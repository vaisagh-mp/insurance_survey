"""
DRF Concurrency Mixin — base_updated_at and ETag / If-Match optimistic concurrency control.

Provides optimistic concurrency control for DRF ModelViewSet endpoints:
1. Optional `base_updated_at` in payload:
   Compares against instance's current `updated_at`. If mismatched, returns HTTP 409 Conflict.
2. Optional `If-Match` header:
   Compares against current ETag (MD5 of pk + updated_at). If mismatched, returns HTTP 409 Conflict.
"""

import hashlib
from datetime import datetime, timezone as dt_timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.response import Response


def compute_etag(instance):
    """
    Compute an ETag string from pk + updated_at.
    Returns a weak ETag like W/"a1b2c3d4e5f6".
    Falls back to pk-only if updated_at is missing.
    """
    updated = getattr(instance, 'updated_at', None) or getattr(instance, 'uploaded_at', None) or getattr(instance, 'created_at', None)
    if updated is not None:
        raw = f"{instance.pk}:{updated.isoformat()}"
    else:
        raw = f"{instance.pk}"
    digest = hashlib.md5(raw.encode()).hexdigest()[:12]
    return f'W/"{digest}"'


def check_optimistic_concurrency(instance, base_updated_at=None, if_match=None):
    """
    Validate optimistic concurrency using base_updated_at or If-Match.
    Returns None if check passes, or a dict with conflict details if mismatch.
    """
    if instance is None:
        return None

    current_updated = getattr(instance, 'updated_at', None) or getattr(instance, 'uploaded_at', None) or getattr(instance, 'created_at', None)
    current_etag = compute_etag(instance)

    # 1. Check base_updated_at from payload
    if base_updated_at and current_updated:
        parsed_base = parse_datetime(str(base_updated_at))
        mismatch = False
        if parsed_base is not None:
            if parsed_base.tzinfo is None:
                parsed_base = parsed_base.replace(tzinfo=dt_timezone.utc)
            if current_updated.tzinfo is None:
                current_dt = current_updated.replace(tzinfo=dt_timezone.utc)
            else:
                current_dt = current_updated
            diff = abs((current_dt - parsed_base).total_seconds())
            if diff > 0.1:
                mismatch = True
        else:
            if str(base_updated_at).strip() != current_updated.isoformat():
                mismatch = True

        if mismatch:
            return {
                'detail': 'Resource has been modified since your base version. Conflict detected.',
                'code': 'conflict',
                'current_updated_at': current_updated.isoformat(),
                'base_updated_at': str(base_updated_at),
                'current_etag': current_etag,
            }

    # 2. Check If-Match header
    if if_match:
        clean_if_match = if_match.strip().strip('"').replace('W/', '')
        clean_current = current_etag.strip().strip('"').replace('W/', '')
        if clean_if_match != clean_current:
            return {
                'detail': 'Resource has been modified since you last fetched it (ETag mismatch).',
                'code': 'conflict',
                'current_etag': current_etag,
            }

    return None


class OptimisticConcurrencyMixin:
    """
    Mixin for DRF ModelViewSet that provides optimistic concurrency control
    via payload `base_updated_at` and/or `If-Match` header.
    """

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        instance = self.get_object()
        response['ETag'] = compute_etag(instance)
        return response

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        conflict = self._check_concurrency(request, instance)
        if conflict:
            return conflict
        response = super().update(request, *args, **kwargs)
        instance.refresh_from_db()
        response['ETag'] = compute_etag(instance)
        return response

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        conflict = self._check_concurrency(request, instance)
        if conflict:
            return conflict
        response = super().partial_update(request, *args, **kwargs)
        instance.refresh_from_db()
        response['ETag'] = compute_etag(instance)
        return response

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        conflict = self._check_concurrency(request, instance)
        if conflict:
            return conflict
        return super().destroy(request, *args, **kwargs)

    def _check_concurrency(self, request, instance):
        """
        Validate optimistic concurrency using base_updated_at or If-Match.
        Returns None if check passes, or a Response(status=409) if conflict.
        """
        base_updated_at = None
        if hasattr(request, 'data') and isinstance(request.data, dict):
            base_updated_at = request.data.get('base_updated_at')
        if not base_updated_at:
            base_updated_at = request.query_params.get('base_updated_at')

        if_match = request.META.get('HTTP_IF_MATCH')

        conflict = check_optimistic_concurrency(instance, base_updated_at=base_updated_at, if_match=if_match)
        if conflict:
            current_etag = conflict.get('current_etag') or compute_etag(instance)
            return Response(
                conflict,
                status=status.HTTP_409_CONFLICT,
                headers={'ETag': current_etag},
            )
        return None


# Backwards compatibility alias
ETagConcurrencyMixin = OptimisticConcurrencyMixin

