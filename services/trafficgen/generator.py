import random
import time

import requests

BASE_URL = "http://nginx:8000"
TENANTS = ["acme", "globex", "initech"]
VALID_PRODUCT_IDS = [1, 2, 3, 4]
MIN_DELAY_SECONDS = 0.5
MAX_DELAY_SECONDS = 2.5


def pick_tenant() -> str:
    return random.choice(TENANTS)


def do_get_products(tenant: str) -> None:
    requests.get(
        f"{BASE_URL}/api/products",
        headers={"X-Tenant": tenant},
        timeout=5,
    )


def do_create_order(tenant: str) -> int | None:
    # Occasionally request a product that doesn't exist, a realistic client mistake.
    product_id = random.choice(VALID_PRODUCT_IDS + [999])
    quantity = random.randint(1, 3)
    response = requests.post(
        f"{BASE_URL}/api/orders",
        headers={"X-Tenant": tenant},
        json={"product_id": product_id, "quantity": quantity},
        timeout=5,
    )
    if response.status_code == 201:
        return response.json()["id"]
    return None


def do_get_order(tenant: str, known_order_ids: list[int]) -> None:
    # Occasionally look up an order that doesn't exist, another realistic case.
    if known_order_ids and random.random() < 0.8:
        order_id = random.choice(known_order_ids)
    else:
        order_id = random.randint(9000, 9999)
    requests.get(
        f"{BASE_URL}/api/orders/{order_id}",
        headers={"X-Tenant": tenant},
        timeout=5,
    )


def do_health_check() -> None:
    requests.get(f"{BASE_URL}/health", timeout=5)


def main() -> None:
    print("trafficgen: starting", flush=True)
    known_order_ids: list[int] = []

    # Give the rest of the stack a moment to finish starting on first boot.
    time.sleep(5)

    while True:
        tenant = pick_tenant()
        action = random.choices(
            population=["get_products", "create_order", "get_order", "health"],
            weights=[35, 25, 30, 10],
            k=1,
        )[0]

        try:
            if action == "get_products":
                do_get_products(tenant)
            elif action == "create_order":
                order_id = do_create_order(tenant)
                if order_id is not None:
                    known_order_ids.append(order_id)
                    known_order_ids[:] = known_order_ids[-50:]  # keep it bounded
            elif action == "get_order":
                do_get_order(tenant, known_order_ids)
            elif action == "health":
                do_health_check()
        except requests.RequestException as exc:
            # The target is temporarily unreachable. Keep going, don't crash.
            print(f"trafficgen: request failed: {exc}", flush=True)

        time.sleep(random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS))


if __name__ == "__main__":
    main()
