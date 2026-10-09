import asyncio

# In-memory fault switches. Restarting the API resets all of them to False.
FAULTS = {
    "force_500": False,
    "slow_requests": False,
    "redis_failure": False,
}

SLOW_REQUEST_DELAY_SECONDS = 2.0


class InjectedFault(Exception):
    """Raised on purpose when the force_500 fault is active."""


async def apply_request_faults() -> None:
    """Called at the start of customer endpoints."""
    if FAULTS["slow_requests"]:
        await asyncio.sleep(SLOW_REQUEST_DELAY_SECONDS)
    if FAULTS["force_500"]:
        raise InjectedFault("force_500 fault is active")
