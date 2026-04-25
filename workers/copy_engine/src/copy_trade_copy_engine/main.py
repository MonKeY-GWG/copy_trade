import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("copy_trade.copy_engine")


async def run() -> None:
    logger.info("copy engine skeleton ready")


if __name__ == "__main__":
    asyncio.run(run())
