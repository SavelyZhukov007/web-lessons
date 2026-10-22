from pydantic import ConfigDict
from .common import Color, InputSchema, Name, UpdateSchema


class CategoryCreate(InputSchema):
    name: Name
    color: Color


class CategoryUpdate(UpdateSchema):
    name: Name | None = None
    color: Color | None = None


class CategoryRead(InputSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Name
    color: Color
