"""Application configuration and environment loading."""

from dotenv import load_dotenv

load_dotenv()

APP_TITLE = "Web Task Orchestrator"
APP_VERSION = "0.1.0"

PINCHTAB_BASE = "http://localhost:9867"
OPENROUTER_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "deepseek/deepseek-v4-pro-0813"

CORS_ORIGINS = ["*"]
CORS_METHODS = ["*"]
CORS_HEADERS = ["*"]
