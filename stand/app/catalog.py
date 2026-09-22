"""The stand's catalogue: eight products, fixed ids, prices as the public API prints them.

Static on purpose: no test creates or deletes a product, and a catalogue that
never moves is what makes the API/UI consistency check and the cart tests
reproducible. Names are chosen so every search term the suite uses — `top`,
`tshirt`, `jean`, `dress` — matches at least one product.
"""
from __future__ import annotations


def _product(product_id: int, name: str, price: int, brand: str, usertype: str, category: str) -> dict:
    return {
        "id": product_id,
        "name": name,
        "price": f"Rs. {price}",
        "brand": brand,
        "category": {"usertype": {"usertype": usertype}, "category": category},
    }


PRODUCTS: list[dict] = [
    _product(1, "Blue Top", 500, "Polo", "Women", "Tops"),
    _product(2, "Men Tshirt", 400, "H&M", "Men", "Tshirts"),
    _product(3, "Sleeveless Dress", 1000, "Madame", "Women", "Dress"),
    _product(4, "Stylish Dress", 1500, "Madame", "Women", "Dress"),
    _product(5, "Winter Top", 600, "Mast & Harbour", "Women", "Tops"),
    _product(6, "Summer White Top", 400, "H&M", "Women", "Tops"),
    _product(7, "Blue Denim Jeans", 1200, "Polo", "Men", "Jeans"),
    _product(8, "Regular Fit Straight Jeans", 1150, "Allen Solly Junior", "Kids", "Jeans"),
]

BRANDS: list[dict] = [
    {"id": index, "brand": brand}
    for index, brand in enumerate(sorted({product["brand"] for product in PRODUCTS}), start=1)
]


def search(query: str) -> list[dict]:
    """Products whose name contains the query, case-insensitively — the public API's rule."""
    needle = query.lower()
    return [product for product in PRODUCTS if needle in product["name"].lower()]


def by_id(product_id: int) -> dict | None:
    return next((product for product in PRODUCTS if product["id"] == product_id), None)
