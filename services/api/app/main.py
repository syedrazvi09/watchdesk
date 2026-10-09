import json
import logging
import os
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.faults import FAULTS, InjectedFault, apply_request_faults
from app.logging_config import configure_logging

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]
PRODUCTS_CACHE_KEY = "products:all"
PRODUCTS_CACHE_TTL_SECONDS = 30
KNOWN_TENANTS = {"acme", "globex", "initech"}

app = FastAPI(title="WatchDesk API")
engine = create_async_engine(DATABASE_URL, pool_size=5, max_overflow=5)
redis = Redis.from_url(REDIS_URL, decode_responses=True)
logger = configure_logging()


class OrderCreate(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=10)


class FaultUpdate(BaseModel):
    enabled: bool


async def get_tenant(x_tenant: str = Header(..., alias="X-Tenant")) -> str:
    tenant = x_tenant.strip().lower()
    if tenant not in KNOWN_TENANTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown tenant '{x_tenant}'. Expected one of {sorted(KNOWN_TENANTS)}.",
        )
    return tenant


async def get_request_id(x_request_id: str | None = Header(default=None, alias="X-Request-ID")) -> str:
    return x_request_id or "unknown"


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    error_text = None
    try:
        response: Response = await call_next(request)
    except Exception as exc:
        # An unhandled exception: return a 500 ourselves so we can still log it.
        error_text = f"{type(exc).__name__}: {exc}"
        response = JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
    latency_ms = round((time.perf_counter() - start) * 1000, 1)

    request_id = request.headers.get("X-Request-ID", "unknown")
    response.headers["X-Request-ID"] = request_id
    tenant = request.headers.get("X-Tenant", "none")

    level = logging.ERROR if response.status_code >= 500 else logging.INFO
    message = f"request failed: {error_text}" if error_text else "request completed"
    logger.log(
        level,
        message,
        extra={
            "request_id": request_id,
            "tenant": tenant,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "latency_ms": latency_ms,
        },
    )
    return response


@app.get("/health")
async def health():
    return {"status": "ok"}


# --- Admin / development controls. Not customer-facing. ---

@app.get("/admin/faults")
async def get_faults():
    return FAULTS


@app.put("/admin/faults/{fault_name}")
async def set_fault(fault_name: str, update: FaultUpdate):
    if fault_name not in FAULTS:
        raise HTTPException(status_code=404, detail=f"Unknown fault '{fault_name}'")
    FAULTS[fault_name] = update.enabled
    logger.warning(f"fault {fault_name} set to {update.enabled}")
    return FAULTS


# --- Customer endpoints ---

@app.get("/api/products")
async def list_products(
    tenant: str = Depends(get_tenant),
    request_id: str = Depends(get_request_id),
):
    await apply_request_faults()

    cached = None
    if not FAULTS["redis_failure"]:
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

    if not FAULTS["redis_failure"]:
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
    await apply_request_faults()

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
    await apply_request_faults()

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
