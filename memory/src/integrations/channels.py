"""
Multi-Channel Integration — Unified adapter for Discord, Telegram, and future channels.

Provides a consistent interface so ClingySOCKs can send/receive from
any messaging platform. The existing Telegram support (in send_message.py
and agent_invoke.py) is wrapped here alongside a new Discord adapter.

Architecture:
    ChannelAdapter (protocol)
    ├── TelegramAdapter — wraps existing _send_telegram_message
    ├── DiscordAdapter — new Discord bot integration
    └── WebhookAdapter — generic webhook for extensibility

Usage:
    from src.integrations.channels import channel_manager
    await channel_manager.send("Hello!", channels=["telegram", "discord"])
    
    # Register incoming message handler
    channel_manager.on_message(my_handler)

Self-contained — does NOT modify existing Telegram code, wraps it.
"""

import os
import logging
import asyncio
from typing import Any, Callable, Awaitable, Optional, Protocol

logger = logging.getLogger("clingysocks.channels")


# ── Channel Protocol ─────────────────────────────────

class ChannelAdapter(Protocol):
    """Protocol all channel adapters must implement."""

    name: str

    async def send(self, content: str, **kwargs) -> dict[str, Any]:
        """Send a message through this channel."""
        ...

    async def is_configured(self) -> bool:
        """Check if this channel has required credentials."""
        ...


# ── Telegram Adapter (wraps existing) ────────────────

class TelegramAdapter:
    name = "telegram"

    async def is_configured(self) -> bool:
        return bool(os.getenv("TELEGRAM_BOT_TOKEN")) and bool(os.getenv("TELEGRAM_CHAT_ID"))

    async def send(self, content: str, **kwargs) -> dict[str, Any]:
        """Send via existing Telegram integration."""
        try:
            from api.routes.agent_invoke import _send_telegram_message
            sent = await _send_telegram_message(content)
            return {"channel": "telegram", "sent": sent}
        except ImportError:
            return {"channel": "telegram", "sent": False, "error": "Telegram module not available"}
        except Exception as e:
            return {"channel": "telegram", "sent": False, "error": str(e)}


# ── Discord Adapter ──────────────────────────────────

class DiscordAdapter:
    """
    Discord integration via webhook (simple) or bot token (full).
    
    Simple mode: Uses DISCORD_WEBHOOK_URL (outbound only, no receiving)
    Bot mode: Uses DISCORD_BOT_TOKEN + DISCORD_CHANNEL_ID (full bidirectional)
    
    Env vars:
        DISCORD_WEBHOOK_URL — For simple outbound-only messages
        DISCORD_BOT_TOKEN — For full bot integration
        DISCORD_CHANNEL_ID — Target channel for bot messages
    """
    name = "discord"

    async def is_configured(self) -> bool:
        return bool(os.getenv("DISCORD_WEBHOOK_URL")) or (
            bool(os.getenv("DISCORD_BOT_TOKEN")) and bool(os.getenv("DISCORD_CHANNEL_ID"))
        )

    async def send(self, content: str, **kwargs) -> dict[str, Any]:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        if webhook_url:
            return await self._send_webhook(webhook_url, content)

        bot_token = os.getenv("DISCORD_BOT_TOKEN")
        channel_id = os.getenv("DISCORD_CHANNEL_ID")
        if bot_token and channel_id:
            return await self._send_bot(bot_token, channel_id, content)

        return {"channel": "discord", "sent": False, "error": "Not configured"}

    async def _send_webhook(self, url: str, content: str) -> dict[str, Any]:
        """Send message via Discord webhook."""
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json={"content": content[:2000]})
                return {"channel": "discord", "sent": resp.status_code in (200, 204)}
        except Exception as e:
            return {"channel": "discord", "sent": False, "error": str(e)}

    async def _send_bot(self, token: str, channel_id: str, content: str) -> dict[str, Any]:
        """Send message via Discord Bot API."""
        import httpx
        try:
            url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
            headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json={"content": content[:2000]}, headers=headers)
                return {"channel": "discord", "sent": resp.status_code == 200}
        except Exception as e:
            return {"channel": "discord", "sent": False, "error": str(e)}


# ── Generic Webhook Adapter ──────────────────────────

class WebhookAdapter:
    """
    Generic webhook adapter for custom integrations.
    
    Env: CUSTOM_WEBHOOK_URL
    """
    name = "webhook"

    async def is_configured(self) -> bool:
        return bool(os.getenv("CUSTOM_WEBHOOK_URL"))

    async def send(self, content: str, **kwargs) -> dict[str, Any]:
        url = os.getenv("CUSTOM_WEBHOOK_URL")
        if not url:
            return {"channel": "webhook", "sent": False, "error": "Not configured"}

        import httpx
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json={
                    "content": content,
                    "source": "clingysocks",
                    **kwargs,
                })
                return {"channel": "webhook", "sent": resp.status_code < 400}
        except Exception as e:
            return {"channel": "webhook", "sent": False, "error": str(e)}


# ── Channel Manager ──────────────────────────────────

class ChannelManager:
    """
    Central manager for all messaging channels.
    
    Registers adapters, sends to multiple channels at once,
    and routes incoming messages to handlers.
    """

    def __init__(self):
        self._adapters: dict[str, ChannelAdapter] = {}
        self._message_handlers: list[Callable[[str, str, dict], Awaitable[None]]] = []

    def register(self, adapter: ChannelAdapter):
        """Register a channel adapter."""
        self._adapters[adapter.name] = adapter

    def on_message(self, handler: Callable[[str, str, dict], Awaitable[None]]):
        """
        Register a handler for incoming messages from any channel.
        
        Handler signature: async def handler(channel: str, content: str, metadata: dict)
        """
        self._message_handlers.append(handler)

    async def get_configured_channels(self) -> list[str]:
        """Return names of all configured channels."""
        configured = []
        for name, adapter in self._adapters.items():
            try:
                if await adapter.is_configured():
                    configured.append(name)
            except Exception:
                pass
        return configured

    async def send(
        self,
        content: str,
        channels: Optional[list[str]] = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Send a message through one or more channels.
        
        Args:
            content: Message text
            channels: List of channel names (None = all configured)
            **kwargs: Extra args passed to adapters
            
        Returns:
            Dict of {channel_name: result}
        """
        if channels is None:
            channels = await self.get_configured_channels()

        results = {}
        tasks = []

        for ch_name in channels:
            adapter = self._adapters.get(ch_name)
            if adapter:
                tasks.append((ch_name, adapter.send(content, **kwargs)))

        for ch_name, coro in tasks:
            try:
                results[ch_name] = await coro
            except Exception as e:
                results[ch_name] = {"channel": ch_name, "sent": False, "error": str(e)}

        return results

    async def dispatch_incoming(self, channel: str, content: str, metadata: dict | None = None):
        """Dispatch an incoming message to all registered handlers."""
        metadata = metadata or {}
        for handler in self._message_handlers:
            try:
                await handler(channel, content, metadata)
            except Exception as e:
                logger.error(f"Message handler error: {e}")


# ── Module-level singleton ───────────────────────────

channel_manager = ChannelManager()
channel_manager.register(TelegramAdapter())
channel_manager.register(DiscordAdapter())
channel_manager.register(WebhookAdapter())
