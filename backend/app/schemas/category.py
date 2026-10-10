from .common import Color, InputSchema, Name, UpdateSchema

class CategoryCreate(InputSchema):
    name: Name
    color: Color

class CategoryUpdate(UpdateSchema):
    name: Name | None = None
    color: Color | None = None