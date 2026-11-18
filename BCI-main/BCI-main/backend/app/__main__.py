import multiprocessing
import uvicorn

from backend.app.infrastructure.config import load_settings
from backend.app.main import create_app

if __name__ == '__main__':
    multiprocessing.freeze_support()
    config = load_settings()
    application = create_app(config)
    server = uvicorn.Server(uvicorn.Config(application, host=config.host, port=config.port, access_log=False))
    def stop():
        server.should_exit = True
    application.state.request_shutdown = stop
    server.run()
