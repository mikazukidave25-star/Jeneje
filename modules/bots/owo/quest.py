import re
import asyncio
import time
import datetime

import discord

from modules.bots.owo.daily import Daily
from modules.utils.component import Component

SPAM_QUEST = [
    r"Say 'owo' [0-9]+ times!",
    r"[0-9]+ xp from hunting and battling!",
    r"Manually hunt [0-9]+ times!",
    r"Hunt [0-9]+ [a-zA-Z]+ rank animals!",
    r"Battle [0-9]+ times!",
]

SINGLE_QUEST = SPAM_QUEST + [
    r"Gamble [0-9]+ times!",
    r"Use an action command on someone [0-9]+ times!",
]

MULTI_QUEST = [
    r"Battle with a friend [0-9]+ times!",
    r"Receive a cookie from [0-9]+ friends!",
    r"Have a friend pray to you [0-9]+ times!",
    r"Have a friend curse you [0-9]+ times!",
    r"Have a friend use an action command on you [0-9]+ times!",
]


class Quest:
    @staticmethod
    def is_single_quest(quest_text):
        return any(re.search(p, quest_text) for p in SINGLE_QUEST)

    @staticmethod
    def is_multi_quest(quest_text):
        return any(re.search(p, quest_text) for p in MULTI_QUEST)

    @staticmethod
    def quest_progress(client, message):
        if not client.doing_quest or not client.current_quest:
            return
        if not client.is_owo_message(message):
            return

        text_complete = f'🎉 | {client.user.mention}, Quest complete:' in message.content
        component_complete = any(
            f'🎉 **|** {client.user.mention}, You completed a quest:' in Component.text(child)
            for child in Component.descendants(message)
        )
        if not (text_complete or component_complete):
            return

        client.logger.info(f'Finished quest: {", ".join(client.current_quest)}')
        client.reset_quest_state()

    @staticmethod
    def _has_quest_log_header(message, user):
        for child in Component.descendants(message):
            if user in Component.text(child):
                return True
        return False

    @staticmethod
    async def _claim_quest(client, message):
        for button in Component.buttons(message):
            if button.custom_id == 'quests:claim' and not button.disabled:
                try:
                    await button.click()
                except discord.HTTPException:
                    client.logger.warning('Failed to claim quest')
                    return False
                client.logger.info('Claimed quest')
                return True
        return False

    @staticmethod
    def _extract_quests(client, message):
        quests = []
        for child in Component.descendants(message):
            content = Component.text(child)
            if not content:
                continue
            for quest in re.findall(r'\n> (.*?)\n>', content):
                quest_text = quest.strip()
                if not quest_text:
                    continue
                if re.search(r"Defeat [0-9]+ boss(es)?!", quest_text):
                    client.logger.info('Detect and skip boss quest')
                    client.config['boss'] = True
                    continue
                if not (Quest.is_single_quest(quest_text) or Quest.is_multi_quest(quest_text)):
                    client.logger.warning(f'Unknown quest: {quest_text}')
                    continue
                quests.append(quest_text)
        return list(dict.fromkeys(quests))

    @staticmethod
    async def do_quest(client):
        if not client.can_run() or not client.config['quest']:
            return
        if client.doing_quest:
            return
        if time.time() < client.cooldown_quest:
            return
        channel = client.current_channel
        if not channel:
            return

        await channel.send(f'{client.prefix}q')
        client.logger.info(f'Sent {client.prefix}q')

        try:
            message = await client.wait_for(
                'message',
                check=lambda m: (
                    client.is_owo_message(m, in_channel=True)
                    and m.components
                    and Quest._has_quest_log_header(m, client.user.mention)
                ),
                timeout=5,
            )

            if await Quest._claim_quest(client, message):
                await asyncio.sleep(2)
                message = await channel.fetch_message(message.id)

            quests = Quest._extract_quests(client, message)
            client.quest_fetched = True
            if not quests:
                wait = Daily.reset_time(client.cooldown_reset)
                client.cooldown_quest = wait + time.time()
                client.logger.info(f'All quests done (next in {datetime.timedelta(seconds=wait)})')
                return

            if len(client.clients) == 1:
                quests = [q for q in quests if Quest.is_single_quest(q)]
                if not quests:
                    wait = Daily.reset_time(client.cooldown_reset)
                    client.cooldown_quest = wait + time.time()
                    client.logger.warning(f'No solo quest available (need multi-account) (next in {datetime.timedelta(seconds=wait)})')
                    return

            client.current_quest = quests
            client.doing_quest = True
            for quest in quests:
                client.logger.info(f'Quest: {quest}')
                Quest.set_quest_flag(client, quest)
        except asyncio.TimeoutError:
            client.logger.warning('Quest fetch timeout')
        except Exception:
            client.logger.exception('Quest fetch error')

    @staticmethod
    def set_spam_flags(client):
        client.quest_flags['owo'] = True
        client.quest_flags['hunt'] = True
        client.quest_flags['battle'] = True

    @staticmethod
    def set_quest_flag(client, quest_text):
        if any(re.search(p, quest_text) for p in SPAM_QUEST):
            Quest.set_spam_flags(client)
        elif re.search(r"Gamble [0-9]+ times!", quest_text):
            client.quest_flags['gamble'] = True
        elif re.search(r"Use an action command on someone [0-9]+ times!", quest_text):
            client.quest_flags['action_someone'] = True
            client.interaction.ensure('action')
        elif re.search(r"Battle with a friend [0-9]+ times!", quest_text):
            client.quest_flags['battle_friend'] = True
            client.interaction.register(client, 'battle')
        elif re.search(r"Receive a cookie from [0-9]+ friends!", quest_text):
            client.quest_flags['cookie'] = True
            client.interaction.register(client, 'cookie')
        elif re.search(r"Have a friend pray to you [0-9]+ times!", quest_text):
            client.quest_flags['pray'] = True
            client.interaction.register(client, 'pray')
        elif re.search(r"Have a friend curse you [0-9]+ times!", quest_text):
            client.quest_flags['curse'] = True
            client.interaction.register(client, 'curse')
        elif re.search(r"Have a friend use an action command on you [0-9]+ times!", quest_text):
            client.quest_flags['action_you'] = True
            client.interaction.register(client, 'action')