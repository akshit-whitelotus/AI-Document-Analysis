from shared.schemas.base import BaseSchema


class RefreshTokenRequest(BaseSchema):
    refresh_token: str