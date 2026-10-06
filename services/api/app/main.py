import json
import os

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]
PRODUCTS_CACHE_KEY = "products:all"
PRODUCTS_CACHE_TTL_SECONDS = 30
KNOWN_TENANTS = {"acme", "globex", "initech"}

app = FastAPI(title="WatchDesk API")
engine = create_async_engine(DATABASE_URL, pool_size=5, max_overflow=5)
redis = Redis.from_url(REDIS_URL, decode_responses=True)


class OrderCreate(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=10)


async def get_tenant(x_tenant: str = Header(..., alias="X-Tenant")) -> str:
    tenant = x_tenant.strip().lower()
    if tenant not in KNOWN_TENANTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown tenant '{x_tenant}'. Expected one of {sorted(KNOWN_TENANTS)}.",
        )
    return tenant


async def get_request_id(x_request_id: str | None = Header(default=None, alias="X-Request-ID")) -> str:
    """Read the request ID Nginx generated. Fall back to 'unknown' if ever missing
    (e.g. a direct call that bypassed Nginx), so downstream code never breaks on it."""
    return x_request_id or "unknown"


@app.middleware("http")
async def add_request_id_response_header(request: Request, call_next):
    response: Response = await call_next(request)
    request_id = request.headers.get("X-Request-ID", "unknown")
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/products")
async def list_products(
    tenant: str = Depends(get_tenant),
    request_id: str = Depends(get_request_id),
):
    try:
        cached = await redis.get(PRODUCTS_CACHE_KEY)
    except Exception:
        cached = None

    if cached is not None:
        return json.loads(cached)

    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT id, name, price FROM products ORDER BY id")
        )
        rows = [dict(r) for r in result.mappings().all()]

    serializable = [
        {**row, "price": float(row["price"])} for row in rows
    ]

    try:
        await redis.set(
            PRODUCTS_CACHE_KEY,
            json.dumps(serializable),
            ex=PRODUCTS_CACHE_TTL_SECONDS,
        )
    except Exception:
        pass

    return serializable


@app.post("/api/orders", status_code=201)
async def create_order(
    order: OrderCreate,
    tenant: str = Depends(get_tenant),
    request_id: str = Depends(get_request_id),
):
    async with engine.begin() as conn:
        product = (
            await conn.execute(
                text("SELECT id, price FROM products WHERE id = :pid"),
                {"pid": order.product_id},
            )
        ).mappings().first()

        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")

        total = round(float(product["price"]) * order.quantity, 2)
        row = (
            await conn.execute(
                text(
                    "INSERT INTO orders (product_id, quantity, total) "
                    "VALUES (:pid, :qty, :total) "
                    "RETURNING id, product_id, quantity, total, status"
                ),
                {"pid": order.product_id, "qty": order.quantity, "total": total},
            )
        ).mappings().first()

    return {**dict(row), "tenant": tenant, "request_id": request_id}


@app.get("/api/orders/{order_id}")
async def get_order(
    order_id: int,
    tenant: str = Depends(get_tenant),
    request_id: str = Depends(get_request_id),
):
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT id, product_id, quantity, total, status "
                    "FROM orders WHERE id = :oid"
                ),
                {"oid": order_id},
            )
        ).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return {**dict(row), "tenant": tenant, "request_id": request_id}
