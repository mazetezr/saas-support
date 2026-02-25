"""Global application state.

Holds references to shared resources initialized during bot startup.
Separated from main.py to avoid circular import issues when handlers
use `from bot.state import ...`.
"""

# Database and cache
db = None               # Database (asyncpg pool)
redis = None            # RedisManager

# ML model
embedding_model = None  # SentenceTransformer

# Services
llm_service = None      # LLMService (shared httpx client)
kb_service = None       # KnowledgeBaseService
conv_service = None     # ConversationService

# Repositories
tenant_repo = None
subscription_repo = None
document_repo = None
chunk_repo = None
message_repo = None
user_settings_repo = None
plan_repo = None

# Bot references
bot_instance = None     # Bot instance for sending messages from workers
bot_username = None     # str: bot's @username
