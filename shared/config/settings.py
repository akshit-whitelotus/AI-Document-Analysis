from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"
class Settings(BaseSettings):
    # PostgreSQL
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    # Redis
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_PASSWORD: str = ""

    # RabbitMQ
    RABBITMQ_HOST: str
    RABBITMQ_PORT: int
    RABBITMQ_USER: str
    RABBITMQ_PASSWORD: str

    # AI
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL:str="gemini-2.0-flash"
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"
    EMBEDDING_MODEL:str = "all-MiniLM-L6-v2"

    #Storage
    UPLOAD_DIR:str="./uploads"
    VECTOR_STORE_DIR:str="./vector_store"
    CHUNK_SIZE:int=800
    CHUNK_OVERLAP:int=100
    # Enforced in both gateway-service (proxy_documents, before the body is 
    # even fully read) and document-service (DocumentService.upload, as it
    # streams to disk) - see the comments at each call site for why both
    # layers check this rather than just one.
    MAX_PDF_UPLOAD_SIZE_BYTES:int= 25*1024*1024 # 25 MB


    #Inter-service URLs (used by gateway-service's ServiceClient)
    AUTH_SERVICE_URL:str="http://localhost:8001"
    DOCUMENT_SERVICE_URL:str="http://localhost:8002"
    CHAT_SERVICE_URL:str="http://localhost:8003"
    AI_WORKER_SERVICE_URL:str="http://localhost:8004"

    #HTTP client policy (shared by every ServiceClient / LLM client)
    HTTP_TIMEOUT_SECONDS:float =15.0
    HTTP_MAX_RETRIES:int = 3

    #Rate limiting
    RATE_LIMIT_PER_MINUTE:int = 60

    # CORS - comma-separated list of allowed origins. Deliberately NOT "*":
    # combined with allow_credentials=True (needed for the Authorization
    # header / bearer tokens the frontend sends), a wildcard origin makes
    # CORSMiddleware reflect back whatever Origin the request came with,
    # which lets any website make authenticated requests on a user's
    # behalf. Keep this to the real, known frontend origin(s).
    CORS_ORIGINS: str = "http://localhost:3000"

    # App
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        extra="ignore"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://"
            f"{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}"
            f"/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()