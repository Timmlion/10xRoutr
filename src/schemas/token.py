# src/schemas/token.py
# (If separating token-related structures further)
# You might place TokenResponse and UserInfo here if desired,
# or keep them in schemas/auth.py as shown above.
# Example:
# from pydantic import BaseModel, UUID4, EmailStr
# from typing import Optional
# from .auth import UserInfo # Assuming UserInfo is defined in auth.py
#
# class Token(BaseModel):
#     access_token: str
#     token_type: str
#
# class TokenData(BaseModel):
#     # Example if decoding JWT payload
#     username: Optional[str] = None
#
# class TokenResponse(BaseModel):
#     access_token: str
#     token_type: str = "bearer"
#     expires_in: Optional[int] = None
#     refresh_token: Optional[str] = None
#     user: UserInfo
