from pydantic import BaseModel, Field
from typing import Optional


class Address(BaseModel):
    street: str
    city: str
    zip_code: str


class CreateAccountRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., pattern=r"^[^@]+@[^@]+$")
    address: Optional[Address] = None
    credit_limit: float = Field(0.0, ge=0)


class AccountResponse(BaseModel):
    id: str
    name: str
    email: str
    active: bool = True
