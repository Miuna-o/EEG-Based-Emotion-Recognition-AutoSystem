"""本地浏览器工作台入口：python -m backend.app。"""
from contextlib import asynccontextmanager
import logging
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

from backend.app.api.routes import router
from backend.app.api.body_limit import BodyLimitMiddleware
from backend.app.application.workspace import Workspace
from backend.app.domain.models import AppError, ErrorResponse
from backend.app.infrastructure.config import PROJECT_ROOT, Settings, load_settings
from backend.app.jobs.executor import Executor


def create_app(settings: Settings | None = None, *, start_worker: bool = True):
    settings = settings or load_settings()
    @asynccontextmanager
    async def lifespan(app):
        app.state.workspace = Workspace(settings)
        app.state.executor = Executor(app.state.workspace)
        if start_worker:
            app.state.executor.start()
        else:
            app.state.executor.recover()
        yield
        app.state.executor.close()

    app = FastAPI(title='心澜本地工作台', version='1.0.0', lifespan=lifespan,
                  responses={422: {'model': ErrorResponse}, 409: {'model': ErrorResponse}, 503: {'model': ErrorResponse}})
    app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_methods=['GET', 'POST', 'PATCH'],
                       allow_headers=['Content-Type'], expose_headers=['X-Request-ID'])

    def error(request, code, message, status, details=None):
        return JSONResponse(status_code=status, content={'code': code, 'message': message, 'details': details,
                                                         'request_id': getattr(request.state, 'request_id', uuid4().hex)})

    @app.middleware('http')
    async def request_context(request: Request, call_next):
        request.state.request_id = uuid4().hex
        try:
            hostname = urlsplit('//' + request.headers.get('host', '')).hostname
        except ValueError:
            hostname = None
        test_client = hostname == 'testserver' and request.client and request.client.host == 'testclient'
        if hostname not in ('localhost', '127.0.0.1', '::1') and not test_client:
            return error(request, 'host_rejected', '仅接受本机服务地址', 400)
        content_length = request.headers.get('content-length')
        if content_length and (not content_length.isdigit() or int(content_length) > (settings.max_upload_mb + 1) * 1024 * 1024):
            return error(request, 'upload_limit', '请求体超过上传限制', 413)
        origin = request.headers.get('origin')
        allowed = settings.allowed_origins + [f'http://127.0.0.1:{settings.port}', f'http://localhost:{settings.port}', f'http://[::1]:{settings.port}']
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin and origin not in allowed:
            return error(request, 'origin_rejected', '请求来源不在本地允许列表中', 403)
        try:
            response = await call_next(request)
        except Exception:
            logging.getLogger('xinlan').error('code=internal_error request_id=%s', request.state.request_id)
            response = error(request, 'internal_error', '服务内部错误；可导出诊断记录排查', 500)
        response.headers['X-Request-ID'] = request.state.request_id
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(AppError)
    async def app_error(request, exc):
        return error(request, exc.code, exc.message, exc.status, exc.details)

    @app.exception_handler(RequestValidationError)
    async def input_error(request, exc):
        details = [{'field': '.'.join(str(part) for part in item['loc']), 'message': item['msg']} for item in exc.errors()]
        return error(request, 'invalid_input', '请求格式或字段不合法', 422, details)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error(request, 'not_found' if exc.status_code == 404 else 'http_error', '资源不存在' if exc.status_code == 404 else '请求无法处理', exc.status_code)

    app.include_router(router)
    frontend = PROJECT_ROOT / 'frontend/dist'
    if (frontend / 'assets').exists():
        app.mount('/assets', StaticFiles(directory=frontend / 'assets'), name='assets')

    @app.get('/{path:path}', include_in_schema=False)
    def frontend_page(path: str):
        if path.startswith('api/'):
            raise AppError('not_found', '接口不存在', 404)
        if (frontend / 'index.html').exists():
            return FileResponse(frontend / 'index.html')
        return JSONResponse({'message': '前端尚未构建，请进入 frontend 执行 npm ci 与 npm run build', 'api_docs': '/docs'}, status_code=503)
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_upload_mb * 1024 * 1024 + 65536)
    return app
