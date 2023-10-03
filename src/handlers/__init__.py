import aiogram


def setup_routers():
    from src.handlers.start import router as start_router
    from src.handlers.emoji_converter import router as emoji_converter_router
    from src.handlers.images import router as images_router
    from src.handlers.videos import router as videos_router
    from src.handlers.errors import router as errors_router

    router = aiogram.Router()
    router.include_router(errors_router)
    router.include_router(start_router)
    router.include_router(emoji_converter_router)
    router.include_router(images_router)
    router.include_router(videos_router)
    return router
