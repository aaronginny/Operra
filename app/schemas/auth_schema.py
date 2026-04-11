from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    company_name: str
    whatsapp_number: str | None = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str | None = None
    token_type: str | None = None
    success: bool = True
    company_id: int | None = None
    error: str | None = None

class CurrentUser(BaseModel):
    id: int
    name: str
    email: str
    company_id: int
    role: str
