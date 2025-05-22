import json
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models import AuditLog, User
from ..db.session import get_db

class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs every HTTP request/response into the audit_logs table.
    """
    async def dispatch(self, request: Request, call_next):
        # 1) Capture request data
        path = request.url.path
        method = request.method
        ip_address = request.client.host if request.client else None

        # Read request body (if JSON)
        try:
            request_body = await request.json()
        except Exception:
            request_body = None

        # 2) Call the actual endpoint
        response: Response = await call_next(request)

        # 3) Capture response data
        status_code = response.status_code
        try:
            response_body = json.loads(response.body.decode())
        except Exception:
            response_body = None

        # 4) Determine user_id (if authenticated)
        db: AsyncSession = request.app.dependency_overrides.get(get_db)
        # Actually, it’s tricky to get AsyncSession from middleware. Instead, queue the write to be run in a background task:
        def _log():
            from ..db.session import SessionLocal  # import inside function to avoid circular import
            sync_db = SessionLocal()
            try:
                # Attempt to get user_id from header Bearer token
                user_id = None
                auth: str = request.headers.get("Authorization", "")
                if auth.lower().startswith("bearer "):
                    token = auth.split(" ")[1]
                    from ..core.security import decode_access_token
                    try:
                        payload = decode_access_token(token)
                        user_id = int(payload.get("sub", 0))
                    except Exception:
                        user_id = None

                log = AuditLog(
                    path=path,
                    method=method,
                    user_id=user_id,
                    status_code=status_code,
                    ip_address=ip_address,
                    request_body=request_body,
                    response_body=response_body
                )
                sync_db.add(log)
                sync_db.commit()
            finally:
                sync_db.close()

        request.app.add_event_handler("shutdown", _log)  # run at end of request

        return response
