from pydantic import BaseModel, Field


class ImageResponse(BaseModel):
    template: str
    display_name: str
    image: str
    description: str
    is_active: bool
    is_default: bool

    model_config = {"from_attributes": True}


class ImageCreateRequest(BaseModel):
    template: str = Field(min_length=1, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*$")
    display_name: str = Field(min_length=1, max_length=64)
    image: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=255)
    is_default: bool = False


class ImageUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=64)
    image: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    is_default: bool | None = None
