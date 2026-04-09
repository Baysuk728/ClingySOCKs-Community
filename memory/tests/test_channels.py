"""Tests for Multi-Channel Integration (channels.py)."""

import pytest


class TestTelegramAdapter:
    """TelegramAdapter — wraps existing Telegram support."""

    @pytest.mark.asyncio
    async def test_not_configured_without_env(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

        from src.integrations.channels import TelegramAdapter
        adapter = TelegramAdapter()
        assert await adapter.is_configured() is False

    @pytest.mark.asyncio
    async def test_configured_with_env(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        from src.integrations.channels import TelegramAdapter
        adapter = TelegramAdapter()
        assert await adapter.is_configured() is True


class TestDiscordAdapter:
    """DiscordAdapter — webhook and bot modes."""

    @pytest.mark.asyncio
    async def test_not_configured_without_env(self, monkeypatch):
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        monkeypatch.delenv("DISCORD_CHANNEL_ID", raising=False)

        from src.integrations.channels import DiscordAdapter
        adapter = DiscordAdapter()
        assert await adapter.is_configured() is False

    @pytest.mark.asyncio
    async def test_configured_with_webhook(self, monkeypatch):
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/fake")

        from src.integrations.channels import DiscordAdapter
        adapter = DiscordAdapter()
        assert await adapter.is_configured() is True

    @pytest.mark.asyncio
    async def test_configured_with_bot(self, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "fake-bot-token")
        monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456")

        from src.integrations.channels import DiscordAdapter
        adapter = DiscordAdapter()
        assert await adapter.is_configured() is True

    @pytest.mark.asyncio
    async def test_send_not_configured(self, monkeypatch):
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        monkeypatch.delenv("DISCORD_CHANNEL_ID", raising=False)

        from src.integrations.channels import DiscordAdapter
        adapter = DiscordAdapter()
        result = await adapter.send("test message")
        assert result["sent"] is False
        assert "error" in result


class TestWebhookAdapter:
    """WebhookAdapter — generic webhook."""

    @pytest.mark.asyncio
    async def test_not_configured_without_env(self, monkeypatch):
        monkeypatch.delenv("CUSTOM_WEBHOOK_URL", raising=False)

        from src.integrations.channels import WebhookAdapter
        adapter = WebhookAdapter()
        assert await adapter.is_configured() is False

    @pytest.mark.asyncio
    async def test_configured_with_env(self, monkeypatch):
        monkeypatch.setenv("CUSTOM_WEBHOOK_URL", "https://example.com/hook")

        from src.integrations.channels import WebhookAdapter
        adapter = WebhookAdapter()
        assert await adapter.is_configured() is True


class TestChannelManager:
    """ChannelManager — send to multiple channels."""

    @pytest.mark.asyncio
    async def test_get_configured_channels(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        monkeypatch.delenv("CUSTOM_WEBHOOK_URL", raising=False)

        from src.integrations.channels import ChannelManager, TelegramAdapter, DiscordAdapter, WebhookAdapter
        mgr = ChannelManager()
        mgr.register(TelegramAdapter())
        mgr.register(DiscordAdapter())
        mgr.register(WebhookAdapter())

        configured = await mgr.get_configured_channels()
        assert "telegram" in configured
        assert "discord" not in configured

    @pytest.mark.asyncio
    async def test_send_to_specific_channels(self, monkeypatch):
        """Send to a named channel, even if not configured."""
        from src.integrations.channels import ChannelManager, DiscordAdapter
        mgr = ChannelManager()
        mgr.register(DiscordAdapter())

        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)

        results = await mgr.send("Hello", channels=["discord"])
        assert "discord" in results
        assert results["discord"]["sent"] is False  # Not configured

    @pytest.mark.asyncio
    async def test_dispatch_incoming(self):
        from src.integrations.channels import ChannelManager

        received = []

        async def handler(channel, content, metadata):
            received.append({"channel": channel, "content": content})

        mgr = ChannelManager()
        mgr.on_message(handler)
        await mgr.dispatch_incoming("telegram", "Hello from Telegram", {})

        assert len(received) == 1
        assert received[0]["channel"] == "telegram"
        assert received[0]["content"] == "Hello from Telegram"
