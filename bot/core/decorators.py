"""Decorators for tenant data isolation enforcement."""

from functools import wraps


class TenantMismatchError(Exception):
    """Raised when a tenant tries to access another tenant's resource."""
    pass


def require_tenant_match(func):
    """Decorator that verifies tenant_id matches the resource's tenant_id.

    Use on service methods that operate on specific resources (documents, etc.)
    to prevent cross-tenant data access.
    """
    @wraps(func)
    async def wrapper(*args, tenant_id, resource_tenant_id, **kwargs):
        if str(tenant_id) != str(resource_tenant_id):
            raise TenantMismatchError(
                f"Tenant {tenant_id} tried to access resource of {resource_tenant_id}"
            )
        return await func(*args, tenant_id=tenant_id, **kwargs)
    return wrapper
