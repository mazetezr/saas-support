"""Allow running as: python -m bot"""

import asyncio
import logging

from bot.main import main

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

try:
    asyncio.run(main())
except KeyboardInterrupt:
    logging.info("Bot stopped by user")
