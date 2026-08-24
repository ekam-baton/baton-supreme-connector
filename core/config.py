from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    api_key: str = "super_secret_connector_key"
    host: str = "0.0.0.0"
    port: int = 8000
    
    class Config:
        env_file = ".env"

settings = Settings()
