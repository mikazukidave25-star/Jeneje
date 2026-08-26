import time

import discord

from modules.utils.logger import get_logger
from modules.utils.data_store import read_lines, deep_merge
from modules.bots.owo.defaults import OWO_DEFAULT_CONFIG
from modules.bots.owo.channel import Channel
from modules.bots.owo.captcha import Captcha
from modules.bots.owo.task import TaskManager
from modules.bots.owo.problem import Problem
from modules.bots.owo.quest import Quest
from modules.bots.owo.boss import Boss
from modules.bots.owo.giveaway import Giveaway
from modules.bots.owo.gem import Gem
from modules.bots.owo.gamble import Gamble


class OWOClient(discord.Client):
    OWO_BOT_ID = 408785106942164992

    def __init__(self, token, config, clients, interaction):
        super().__init__()
        self.token = token
        self.config = deep_merge(OWO_DEFAULT_CONFIG, config or {})
        self.clients = clients
        self.interaction = interaction
        self.bot_name = 'owo'
        self.prefix = self.config['prefix']

        self.owo_bot = None
        self.current_channel = None
        self.current_channel_id = None
        self.nickname = ''

        self.macro_enabled = False
        self.captcha_pending = False
        self.paused = False
        self.is_blocked = False

        self.cooldown_quest = 0
        self.cooldown_daily = 0
        self.cooldown_boss = 0
        self.cooldown_huntbot = 0
        self.cooldown_glitch = 0
        self.cooldown_lottery = 0
        self.cooldown_reset = 0

        if self.config['checklist']:
            self.config['quest'] = self.config['vote'] = self.config['daily'] = self.config['boss'] = True
        self.checklist_spam = False
        self.cookie_available = False
        self.cookie_cooldown = 0
        self.interaction_cd = {'pray': 0, 'curse': 0, 'battle': 0, 'action': 0}

        self.doing_quest = False
        self.quest_fetched = False
        self.current_quest = []
        self.quest_flags = {
            'owo': False, 'hunt': False, 'battle': False,
            'gamble': False, 'action_someone': False,
            'battle_friend': False, 'cookie': False,
            'pray': False, 'curse': False, 'action_you': False,
        }

        if int(self.config['gamble']['highlow']['bet']) < 10:
            self.config['gamble']['highlow']['bet'] = 10
        self.bet_slot = int(self.config['gamble']['slot']['bet'])
        self.bet_coinflip = int(self.config['gamble']['coinflip']['bet'])
        self.bet_blackjack = int(self.config['gamble']['blackjack']['bet'])
        self.bet_highlow = int(self.config['gamble']['highlow']['bet'])

        self.ga_joined = set()
        self.block_battle = False
        self.no_gem = False
        self.no_gem_since = 0
        self.special_pet_available = True
        self.inventory_str = 'gem1 gem3 gem4 star'
        self.last_owo_message_time = time.time()

        self.task_manager = None
        self.logger = None
        self._on_ready_done = False
        self._current_captcha_id = None
        self._current_answer = ''

        self.owo_actions = read_lines('assets/owo/actions.txt')

    def can_run(self):
        return self.macro_enabled and not self.captcha_pending and not self.paused and not self.is_blocked

    async def on_ready(self):
        if not self.logger:
            self.logger = get_logger(self.user.name)

        self.owo_bot = self.get_user(self.OWO_BOT_ID)
        if not self.owo_bot:
            self.logger.critical('OWO bot not found, ensure the account shares a server with OWO')
            return

        try:
            await self.owo_bot.create_dm()
        except Exception:
            self.logger.exception('Failed to open OWO DM')

        await Captcha.process_pending(self)
        await Channel.init_channel(self)

        if self._on_ready_done:
            self.logger.info('Reconnected')
            return

        self._on_ready_done = True
        self.task_manager = TaskManager(self)
        self.logger.info(f'Ready in #{self.current_channel} ({self.current_channel_id})')
        await self.task_manager.start()

    async def on_message(self, message):
        if not self.owo_bot:
            return

        if message.author.id == self.owo_bot.id:
            self.last_owo_message_time = time.time()

        await Captcha.detect(self, message)
        Problem.check(self, message)

        if not self.can_run():
            return

        changing_channel = self.config['changing_channel']
        if changing_channel['when_mentioned']:
            await Channel.change_when_mentioned(self, message)
        if changing_channel['when_challenge'] or self.quest_flags.get('battle_friend'):
            await Channel.accept_challenge(self, message)

        if self.config['quest']:
            Quest.quest_progress(self, message)

        if self.config['boss']:
            await Boss.handle(self, message)

        if self.config['gem']['use'] or Gem.glitch_available(self):
            await Gem.check_gem(self, message)

    async def on_message_edit(self, before, after):
        if not self.can_run() or not self.owo_bot:
            return

        if self.config['giveaway']:
            await Giveaway.join(self, after)

        gamble = self.config['gamble']
        if gamble['slot']['mode'] or self.quest_flags.get('gamble'):
            Gamble.check_slot(self, after)
        if gamble['coinflip']['mode'] or self.quest_flags.get('gamble'):
            Gamble.check_coinflip(self, after)

    def is_owo_message(self, message, in_channel=False):
        if message.author.id != self.owo_bot.id:
            return False
        if in_channel and message.channel.id != self.current_channel_id:
            return False
        return True

    @staticmethod
    def message_contains(message, all_of=None, any_of=None):
        if all_of and not all(content in message for content in all_of):
            return False
        if any_of and not any(content in message for content in any_of):
            return False
        return True

    async def stop_runtime(self):
        if self.task_manager:
            await self.task_manager.stop()
        if not self.is_closed():
            await self.close()

    def reset_quest_state(self):
        self.doing_quest = False
        self.quest_fetched = False
        self.current_quest = []
        if self.interaction:
            for kind in ('pray', 'curse', 'battle', 'action', 'cookie'):
                self.interaction.unregister(self, kind)
        self.quest_flags = {k: False for k in self.quest_flags}
        self.block_battle = False