from pydantic import BaseModel


class ApiKeyModel(BaseModel):
    exchange: str
    api_key: str
    api_secret: str
