"""在 multipart 解析与临时落盘之前限制完整请求体，覆盖 chunked 上传。"""
import io
from uuid import uuid4
from starlette.responses import JSONResponse


class BodyLimitMiddleware:
    def __init__(self, app, max_bytes):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in ('POST', 'PATCH', 'PUT'):
            return await self.app(scope, receive, send)
        buffer = io.BytesIO()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            if buffer.tell() + len(chunk) > self.max_bytes:
                response = JSONResponse({'code': 'upload_limit', 'message': '请求体超过上传限制，未解析或写入文件',
                                         'details': None, 'request_id': uuid4().hex}, status_code=413)
                return await response(scope, receive, send)
            buffer.write(chunk)
            if not message.get('more_body', False):
                break
        delivered = False
        async def limited_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': buffer.getvalue(), 'more_body': False}
            return await receive()
        await self.app(scope, limited_receive, send)
