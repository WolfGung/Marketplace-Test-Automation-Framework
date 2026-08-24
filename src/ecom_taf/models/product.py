from pydantic import BaseModel, Field


class UserType(BaseModel):
    usertype: str


class Category(BaseModel):
    usertype: UserType
    category: str


class Product(BaseModel):
    id: int
    name: str
    price: str
    brand: str
    category: Category


class ProductsResponse(BaseModel):
    response_code: int = Field(alias="responseCode")
    products: list[Product] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
