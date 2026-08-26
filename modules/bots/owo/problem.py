class Problem:
    @staticmethod
    def check(client, message):
        if not client.is_owo_message(message):
            return

        content = message.content

        if 'You have been banned' in content:
            is_relevant = (
                str(client.user.name) in content
                or (client.owo_bot and hasattr(client.owo_bot, 'dm_channel')
                    and client.owo_bot.dm_channel
                    and message.channel.id == client.owo_bot.dm_channel.id)
            )
            if is_relevant:
                client.is_blocked = True
                client.logger.critical('Banned, macro stopped')
                return

        if "don't have enough cowoncy" in content and str(client.nickname) in content and 'you silly hooman' not in content:
            client.is_blocked = True
            client.logger.critical('Run out of cowoncy, macro stopped')