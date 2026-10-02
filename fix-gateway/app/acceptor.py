import asyncio
import logging

from app.config import settings
from app.message_handlers import handle_application_message
from app.session import FixSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fix-gateway")


async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peer = writer.get_extra_info("peername")
    logger.info("FIX session connected from %s", peer)
    session = FixSession(reader, writer, on_message=handle_application_message)
    try:
        await session.run()
    finally:
        logger.info("FIX session from %s disconnected", peer)


async def serve() -> None:
    server = await asyncio.start_server(_handle_client, settings.listen_host, settings.listen_port)
    logger.info("FIX acceptor listening on %s:%s", settings.listen_host, settings.listen_port)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(serve())
