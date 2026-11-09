import os


class DefaultConfig:
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    API_TITLE = "Product API - INT3505E"
    API_VERSION = "1.0.0"
    OPENAPI_VERSION = "3.0.3"
    OPENAPI_URL_PREFIX = "/"
    OPENAPI_JSON_PATH = "openapi.json"
    OPENAPI_SWAGGER_UI_PATH = "/docs"
    OPENAPI_SWAGGER_UI_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/"
    MAX_CONTENT_LENGTH = 1024 * 1024

    def __init__(self):
        self.SECRET_KEY = os.getenv("SECRET_KEY", "local-development-key")
        self.SQLALCHEMY_DATABASE_URI = os.getenv("DB_URL", "sqlite:///dev.db")
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}


class TestConfig(DefaultConfig):
    TESTING = True

    def __init__(self):
        super().__init__()
        self.SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        self.LOG_LEVEL = "WARNING"


class ProductionConfig(DefaultConfig):
    def __init__(self):
        super().__init__()
        if not os.getenv("SECRET_KEY") or self.SECRET_KEY == "local-development-key":
            raise ValueError("Production requires a private SECRET_KEY")
        if not self.SQLALCHEMY_DATABASE_URI.startswith("sqlite"):
            self.SQLALCHEMY_ENGINE_OPTIONS.update(
                pool_size=10, max_overflow=20, pool_recycle=1800, pool_timeout=30
            )
