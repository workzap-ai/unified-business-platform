"""Code-side product definitions. The platform_products table mirrors these rows.

A new installable product registers one ProductDefinition here (plus a migration or
`sync_products` call to insert its catalog row). Install hooks provision its
per-environment defaults; they must be idempotent.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.scope import WorkspaceScope

InstallHook = Callable[[AsyncSession, WorkspaceScope], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ProductDefinition:
    key: str
    name: str
    description: str
    category: str
    features: tuple[str, ...] = ()
    install_hooks: list[InstallHook] = field(default_factory=list, compare=False)


class ProductRegistry:
    def __init__(self) -> None:
        self._products: dict[str, ProductDefinition] = {}

    def register(self, product: ProductDefinition) -> ProductDefinition:
        if product.key in self._products:
            raise ValueError(f"Product {product.key} is already registered")
        self._products[product.key] = product
        return product

    def get(self, key: str) -> ProductDefinition | None:
        return self._products.get(key)

    def all(self) -> list[ProductDefinition]:
        return sorted(self._products.values(), key=lambda p: p.name)

    def on_install(self, key: str) -> Callable[[InstallHook], InstallHook]:
        def decorator(hook: InstallHook) -> InstallHook:
            product = self._products[key]
            product.install_hooks.append(hook)
            return hook

        return decorator


PRODUCTS = ProductRegistry()

PI = PRODUCTS.register(
    ProductDefinition(
        key="pi",
        name="PI",
        description=(
            "AI WhatsApp customer assistant: answers questions from verified company data, "
            "checks stock, drafts orders and quotes, and hands off to your team."
        ),
        category="ai",
        features=("text", "voice", "vision", "knowledge", "orders", "quotes", "handoff"),
    )
)
