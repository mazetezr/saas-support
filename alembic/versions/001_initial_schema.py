"""Initial schema for SaaS multi-tenant support bot.

Revision ID: 001
Create Date: 2026-02-19
"""

from alembic import op

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # --- Tenants ---
    op.execute("""
        CREATE TABLE tenants (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            owner_user_id BIGINT NOT NULL UNIQUE,
            project_name TEXT NOT NULL,
            chat_id BIGINT UNIQUE,
            chat_title TEXT,
            moderator_usernames TEXT[] DEFAULT '{}',
            persona_doc TEXT,
            language TEXT DEFAULT 'ru',
            relevance_threshold FLOAT DEFAULT 0.75,
            openrouter_api_key TEXT NOT NULL,
            status TEXT DEFAULT 'trial',
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_tenants_owner ON tenants(owner_user_id)")
    op.execute("CREATE INDEX idx_tenants_chat_id ON tenants(chat_id)")
    op.execute("CREATE INDEX idx_tenants_status ON tenants(status)")

    # --- Plans ---
    op.execute("""
        CREATE TABLE plans (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            max_chunks INT NOT NULL,
            price_usd DECIMAL(10,2) NOT NULL,
            duration_days INT DEFAULT 30
        )
    """)
    # Seed plan data
    op.execute("""
        INSERT INTO plans (name, max_chunks, price_usd, duration_days) VALUES
        ('lite',     20,  5.00,  30),
        ('standard', 50,  9.00,  30),
        ('pro',      100, 19.00, 30),
        ('business', 200, 39.00, 30)
    """)

    # --- Subscriptions ---
    op.execute("""
        CREATE TABLE subscriptions (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            plan_id INT REFERENCES plans(id),
            status TEXT DEFAULT 'active',
            started_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP NOT NULL,
            payment_provider TEXT DEFAULT 'cryptocloud',
            payment_invoice_id TEXT,
            payment_amount DECIMAL(10,2),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_subscriptions_tenant ON subscriptions(tenant_id)")
    op.execute("CREATE INDEX idx_subscriptions_expires ON subscriptions(expires_at) WHERE status = 'active'")
    op.execute("CREATE INDEX idx_subscriptions_invoice ON subscriptions(payment_invoice_id)")

    # --- User Settings ---
    op.execute("""
        CREATE TABLE user_settings (
            user_id BIGINT PRIMARY KEY,
            current_tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # --- Documents ---
    op.execute("""
        CREATE TABLE documents (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            filename TEXT NOT NULL,
            chunk_count INT DEFAULT 0,
            uploaded_by BIGINT NOT NULL,
            status TEXT DEFAULT 'processing',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_documents_tenant ON documents(tenant_id)")

    # --- Chunks (replaces ChromaDB) ---
    op.execute("""
        CREATE TABLE chunks (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            chunk_index INT NOT NULL,
            content TEXT NOT NULL,
            embedding vector(384),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_chunks_tenant ON chunks(tenant_id)")
    op.execute("CREATE INDEX idx_chunks_document ON chunks(document_id)")
    # HNSW index for fast cosine similarity search
    op.execute("""
        CREATE INDEX idx_chunks_embedding ON chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # --- Messages ---
    op.execute("""
        CREATE TABLE messages (
            id BIGSERIAL PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL,
            chat_id BIGINT NOT NULL,
            chat_type TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_messages_tenant ON messages(tenant_id)")
    op.execute("CREATE INDEX idx_messages_user_chat ON messages(user_id, chat_id)")
    op.execute("CREATE INDEX idx_messages_time ON messages(created_at)")

    # --- Conversation Summaries ---
    op.execute("""
        CREATE TABLE conversation_summaries (
            id BIGSERIAL PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL,
            chat_id BIGINT NOT NULL,
            summary TEXT NOT NULL,
            messages_from BIGINT NOT NULL,
            messages_to BIGINT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_summaries_tenant ON conversation_summaries(tenant_id)")
    op.execute("CREATE INDEX idx_summaries_user_chat ON conversation_summaries(user_id, chat_id)")

    # --- FAQ Candidates ---
    op.execute("""
        CREATE TABLE faq_candidates (
            id BIGSERIAL PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            frequency INT DEFAULT 1,
            source_message_ids TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_faq_tenant ON faq_candidates(tenant_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS faq_candidates CASCADE")
    op.execute("DROP TABLE IF EXISTS conversation_summaries CASCADE")
    op.execute("DROP TABLE IF EXISTS messages CASCADE")
    op.execute("DROP TABLE IF EXISTS chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS documents CASCADE")
    op.execute("DROP TABLE IF EXISTS user_settings CASCADE")
    op.execute("DROP TABLE IF EXISTS subscriptions CASCADE")
    op.execute("DROP TABLE IF EXISTS plans CASCADE")
    op.execute("DROP TABLE IF EXISTS tenants CASCADE")
