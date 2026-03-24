"""Multi-tenant middleware."""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

PUBLIC_PATHS = {"/api/v1/health", "/api/v1/auth/login", "/api/v1/auth/register", "/metrics", "/api/docs", "/api/redoc"}


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if any(request.url.path.startswith(p) for p in PUBLIC_PATHS):
            return await call_next(request)

        tenant_id = self._extract_tenant_id(request)
        request.state.tenant_id = tenant_id

        return await call_next(request)

    @staticmethod
    def _extract_tenant_id(request: Request) -> str | None:
        if tenant_id := request.headers.get("X-Tenant-ID"):
            return tenant_id
        return None
