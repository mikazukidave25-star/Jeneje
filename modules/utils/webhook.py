import discord
import aiohttp
import datetime

from modules.utils.logger import get_logger

logger = get_logger('webhook')


class DiscordWebhook:
    @staticmethod
    async def send(webhook_url, user_name, user_avatar, content, title=None, description=None, color=None, image=None, thumbnail=None):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                webhook = discord.Webhook.from_url(webhook_url, session=session)
                if title:
                    embed = discord.Embed(title=title, description=description, color=color)
                    embed.set_author(name=user_name, icon_url=user_avatar)
                    if image:
                        embed.set_image(url=image)
                    if thumbnail:
                        embed.set_thumbnail(url=thumbnail)
                    embed.timestamp = datetime.datetime.now()
                    embed.set_footer(text='Phamdat Selfbot', icon_url='https://raw.githubusercontent.com/realphamdat/phamdat-selfbot/refs/heads/main/assets/logo.png')
                    await webhook.send(content=content, embed=embed)
                else:
                    await webhook.send(content=content)
        except Exception:
            logger.exception('Failed to send webhook')