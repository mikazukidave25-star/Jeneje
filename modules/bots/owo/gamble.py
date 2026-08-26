import asyncio
import re
import random
import time
import datetime

import discord

from modules.bots.owo.daily import Daily
from modules.utils.component import Component


class Gamble:
    @staticmethod
    def check_slot(client, message):
        if not client.can_run():
            return
        if not client.is_owo_message(message, in_channel=True):
            return
        if str(client.nickname) not in message.content:
            return

        content = message.content
        if 'won nothing' in content:
            client.logger.info(f'Slot lost {client.bet_slot}')
            client.bet_slot *= int(client.config['gamble']['slot']['rate'])
        elif '<:eggplant:417475705719226369> <:eggplant:417475705719226369> <:eggplant:417475705719226369>' in content:
            client.logger.info(f'Slot draw {client.bet_slot}')
        elif '<:heart:417475705899712522> <:heart:417475705899712522> <:heart:417475705899712522>' in content:
            client.logger.info(f'Slot won {client.bet_slot * 2} (x2)')
            client.bet_slot = int(client.config['gamble']['slot']['bet'])
        elif '<:cherry:417475705178161162> <:cherry:417475705178161162> <:cherry:417475705178161162>' in content:
            client.logger.info(f'Slot won {client.bet_slot * 3} (x3)')
            client.bet_slot = int(client.config['gamble']['slot']['bet'])
        elif '<:cowoncy:417475705912426496> <:cowoncy:417475705912426496> <:cowoncy:417475705912426496>' in content:
            client.logger.info(f'Slot won {client.bet_slot * 4} (x4)')
            client.bet_slot = int(client.config['gamble']['slot']['bet'])
        elif '<:o_:417475705899843604> <:w_:417475705920684053> <:o_:417475705899843604>' in content:
            client.logger.info(f'Slot won {client.bet_slot * 10} (x10)')
            client.bet_slot = int(client.config['gamble']['slot']['bet'])

    @staticmethod
    def check_coinflip(client, message):
        if not client.can_run():
            return
        if not client.is_owo_message(message, in_channel=True):
            return
        if str(client.nickname) not in message.content:
            return

        if 'you lost' in message.content:
            client.logger.info(f'Coinflip lost {client.bet_coinflip}')
            client.bet_coinflip *= int(client.config['gamble']['coinflip']['rate'])
        elif 'you won' in message.content:
            client.logger.info(f'Coinflip won {client.bet_coinflip}')
            client.bet_coinflip = int(client.config['gamble']['coinflip']['bet'])

    @staticmethod
    async def lottery(client):
        if not client.can_run():
            return
        lottery = client.config['gamble']['lottery']
        if not lottery['mode']:
            return
        if time.time() < client.cooldown_lottery:
            return
        if not client.current_channel:
            return

        amount = lottery['amount']
        await client.current_channel.send(f'{client.prefix}lottery {amount}')
        client.logger.info(f'Sent {client.prefix}lottery {amount}')

        try:
            await client.wait_for(
                'message',
                check=lambda m: (
                    client.is_owo_message(m, in_channel=True)
                    and m.embeds
                    and str(m.embeds[0].author.name) == f"{client.nickname}'s Lottery Submission"
                ),
                timeout=5,
            )
        except asyncio.TimeoutError:
            client.logger.warning('Lottery message timeout')
            return

        wait = Daily.reset_time(client.cooldown_reset)
        client.cooldown_lottery = wait + time.time()
        client.logger.info(f'Lottery ends in {datetime.timedelta(seconds=wait)}')

    @staticmethod
    async def play_slot(client):
        if not client.can_run() or not client.current_channel:
            return

        max_bet = int(client.config['gamble']['slot']['max'])
        if client.bet_slot > max_bet:
            client.bet_slot = int(client.config['gamble']['slot']['bet'])

        await client.current_channel.send(f'{client.prefix}s {client.bet_slot}')
        client.logger.info(f'Sent {client.prefix}s {client.bet_slot}')

    @staticmethod
    async def play_coinflip(client):
        if not client.can_run() or not client.current_channel:
            return

        max_bet = int(client.config['gamble']['coinflip']['max'])
        if client.bet_coinflip > max_bet:
            client.bet_coinflip = int(client.config['gamble']['coinflip']['bet'])

        await client.current_channel.send(f'{client.prefix}cf {client.bet_coinflip}')
        client.logger.info(f'Sent {client.prefix}cf {client.bet_coinflip}')

    @staticmethod
    async def play_blackjack(client):
        if not client.can_run() or not client.current_channel:
            return

        max_bet = int(client.config['gamble']['blackjack']['max'])
        if client.bet_blackjack > max_bet:
            client.bet_blackjack = int(client.config['gamble']['blackjack']['bet'])

        await client.current_channel.send(f'{client.prefix}bj {client.bet_blackjack}')
        client.logger.info(f'Sent {client.prefix}bj {client.bet_blackjack}')

        try:
            blackjack_message = await client.wait_for(
                'message',
                check=lambda m: (
                    client.is_owo_message(m, in_channel=True)
                    and m.embeds
                    and str(client.user.name) in str(m.embeds[0].author.name)
                    and 'play blackjack' in str(m.embeds[0].author.name)
                ),
                timeout=5,
            )
        except asyncio.TimeoutError:
            client.logger.warning('Blackjack message timeout')
            return

        for _ in range(20):
            await asyncio.sleep(2)
            try:
                blackjack_message = await client.current_channel.fetch_message(blackjack_message.id)
            except Exception:
                break

            footer = str(blackjack_message.embeds[0].footer.text) if blackjack_message.embeds[0].footer else ''

            if 'in progress' in footer or 'resuming previous' in footer:
                points = re.findall(r'\[(.*?)\]', blackjack_message.embeds[0].fields[1].name)
                if points:
                    my_points = int(points[0])
                    emoji = '👊' if my_points <= 17 else '🛑'
                    has_reacted = any(reaction.me for reaction in blackjack_message.reactions)
                    try:
                        if emoji == '👊':
                            if has_reacted:
                                await blackjack_message.remove_reaction(emoji, client.user)
                            else:
                                await blackjack_message.add_reaction(emoji)
                            client.logger.info(f'Blackjack {my_points} pts (Hit) - {"Remove" if has_reacted else "Add"} reaction')
                        else:
                            await blackjack_message.add_reaction(emoji)
                            client.logger.info(f'Blackjack {my_points} pts (Stand)')
                    except Exception:
                        client.logger.exception('Failed to react blackjack')
            elif 'You won' in footer:
                client.logger.info(f'Blackjack won {client.bet_blackjack}')
                client.bet_blackjack = int(client.config['gamble']['blackjack']['bet'])
                break
            elif 'You lost' in footer:
                client.logger.info(f'Blackjack lost {client.bet_blackjack}')
                client.bet_blackjack *= int(client.config['gamble']['blackjack']['rate'])
                break
            elif 'You tied' in footer or 'You both bust' in footer:
                client.logger.info('Blackjack draw')
                break
            else:
                break

    @staticmethod
    def _is_highlow_start(client, message):
        if not message.components:
            return False
        text = Component.text(message.components[0])
        return client.message_contains(text, all_of=[client.user.mention, '**Bet**:', '**Streak**:', '**Cash Out**:'])

    @staticmethod
    async def play_highlow(client):
        if not client.can_run() or not client.current_channel:
            return

        highlow = client.config['gamble']['highlow']
        if client.bet_highlow > int(highlow['max']):
            client.bet_highlow = int(highlow['bet'])

        await client.current_channel.send(f'{client.prefix}hl {client.bet_highlow}')
        client.logger.info(f'Sent {client.prefix}hl {client.bet_highlow}')

        try:
            message = await client.wait_for(
                'message',
                check=lambda m: Gamble._is_highlow_start(client, m),
                timeout=5,
            )
        except asyncio.TimeoutError:
            client.logger.warning('HighLow message timeout')
            return

        for _ in range(20):
            await asyncio.sleep(2)
            try:
                message = await client.current_channel.fetch_message(message.id)
            except discord.HTTPException:
                break
            if await Gamble._handle_highlow(client, message):
                break

    @staticmethod
    async def _handle_highlow(client, message):
        text = Component.text(message)
        match = re.search(r'\(([\d.]+)x\)', text)
        if match: multiple = float(match.group(1))

        if 'cashed out!' in text:
            client.logger.info(f'HighLow won {client.bet_highlow * multiple} (x{multiple})')
            client.bet_highlow = int(client.config['gamble']['highlow']['bet'])
            return True

        if 'guessed incorrectly!' in text:
            client.logger.info(f'HighLow lost {client.bet_highlow}')
            client.bet_highlow *= int(client.config['gamble']['highlow']['rate'])
            return True

        if multiple >= 2.0:
            return await Gamble._highlow_cashout(client, message)

        return await Gamble._highlow_guess(client, message)

    @staticmethod
    async def _highlow_cashout(client, message):
        for button in Component.buttons(message):
            if 'cashout' in (button.custom_id or '') and not button.disabled:
                try:
                    await button.click()
                except discord.HTTPException:
                    client.logger.exception('Failed to click highlow cashout')
                    return True
                client.logger.info('HighLow cashed out')
                return False
        client.logger.warning('HighLow cashout button not found')
        return True

    @staticmethod
    async def _highlow_guess(client, message):
        guesses = []
        for button in Component.buttons(message):
            match = re.match(r'(Higher|Lower) \(\+([\d,]+)\)', button.label or '')
            if match and not button.disabled:
                guesses.append((int(match.group(2).replace(',', '')), button))
        if not guesses:
            client.logger.warning('HighLow guess buttons not found')
            return True
        value, button = min(guesses, key=lambda item: item[0])
        try:
            await button.click()
        except discord.HTTPException:
            client.logger.exception('Failed to click highlow guess')
            return True
        client.logger.info(f'HighLow guessed {button.label}')
        return False

    @staticmethod
    async def gamble_cycle(client):
        gamble = client.config['gamble']
        delay_min = gamble['delay']['min']
        delay_max = gamble['delay']['max']

        try:
            if gamble['lottery']['mode']:
                await Gamble.lottery(client)
                await asyncio.sleep(random.uniform(delay_min, delay_max))

            if gamble['slot']['mode'] or client.quest_flags.get('gamble'):
                await Gamble.play_slot(client)
                await asyncio.sleep(random.uniform(delay_min, delay_max))

            if gamble['coinflip']['mode'] or client.quest_flags.get('gamble'):
                await Gamble.play_coinflip(client)
                await asyncio.sleep(random.uniform(delay_min, delay_max))

            if gamble['blackjack']['mode'] or client.quest_flags.get('gamble'):
                await Gamble.play_blackjack(client)
                await asyncio.sleep(random.uniform(delay_min, delay_max))

            if gamble['highlow']['mode'] or client.quest_flags.get('gamble'):
                await Gamble.play_highlow(client)
        except Exception:
            client.logger.exception('Gamble error')