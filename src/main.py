import asyncio
import logging
import signal
from aiohttp import web
from src.database import init_db
from src.bot import create_bot_app
from src.config import PORT

# Configuração de logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("liam")


async def health_check(request):
    """Endpoint de verificação de saúde para a Render ou monitoramento."""
    return web.json_response({
        "status": "healthy",
        "bot": "Liam",
        "description": "Assistente de Saúde da Família"
    })


async def start_web_server():
    """Inicia um servidor web leve para satisfazer a porta exigida pela Render."""
    web_app = web.Application()
    web_app.router.add_get("/", health_check)
    web_app.router.add_get("/health", health_check)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"🌐 Servidor de healthcheck rodando na porta {PORT}")
    return runner


async def main():
    logger.info("🩺 Inicializando o banco de dados do Liam...")
    await init_db()

    # Inicia servidor web de healthcheck
    web_runner = await start_web_server()

    # Cria e inicia o bot do Telegram
    bot_app = create_bot_app()
    logger.info("🚀 Conectando o Liam ao Telegram...")

    async with bot_app:
        await bot_app.initialize()
        await bot_app.start()
        await bot_app.updater.start_polling(drop_pending_updates=True)
        logger.info("✨ Liam está online e pronto para gerenciar suas consultas e receitas!")

        stop_event = asyncio.Event()

        # Tratamento de encerramento gracioso (SIGINT / SIGTERM)
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:
                # Windows pode não suportar add_signal_handler
                pass

        try:
            await stop_event.wait()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            logger.info("Encerrando o Liam com segurança...")
            if bot_app.updater.running:
                await bot_app.updater.stop()
            await bot_app.stop()
            await web_runner.cleanup()
            logger.info("Liam finalizado.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Execução finalizada.")
