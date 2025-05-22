import msgpack
from fastapi import Request
from fastapi.responses import Response

MSGPACK_MIME = "application/x-msgpack"

class MessagePackResponse(Response):
    media_type = MSGPACK_MIME

    def render(self, content: any) -> bytes:
        return msgpack.packb(content, use_bin_type=True)


async def msgpack_or_json(request: Request, call_next):
    response = await call_next(request)

    if isinstance(response, MessagePackResponse):
        return response

    accept_header = request.headers.get("accept", "")
    if MSGPACK_MIME in accept_header.lower():
        try:
            data = response.json()
        except Exception:
            return response
        return MessagePackResponse(content=data, status_code=response.status_code)
    else:
        return response
