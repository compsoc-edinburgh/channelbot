#!/usr/bin/env python3
import os
import sys
import traceback


import discord

from discord.ext import commands

import secrets as config

INTENTS = discord.Intents.default()
INTENTS.members = True

CLIENT = commands.Bot(command_prefix=commands.when_mentioned_or("§"), intents=INTENTS)


def in_managed_channnel(ctx):
    return ctx.message.channel.id in [
        config["channel_id"] for config in config.CHANNELS
    ]


@CLIENT.event
async def on_ready():
    print(f"Logged in to Discord as {CLIENT.user}")


def should_manage_from_reaction_emoji(channel_config, payload):
    guild = CLIENT.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)

    if config.PREREQUISITE_ROLE_ID:
        prerequisite_found = False
        for role in member.roles:
            if role.id == config.PREREQUISITE_ROLE_ID:
                prerequisite_found = True

        if not prerequisite_found:
            return

    if channel_config.get("reaction_channel") != payload.channel_id:
        return False

    if channel_config.get("reaction_message") != payload.message_id:
        return False

    # Emoji Check
    target = channel_config.get("reaction_emoji")
    received = payload.emoji
    print(received.name.encode("raw_unicode_escape"), target)
    if type(target) == bytes and received.is_unicode_emoji():
        return target == received.name.encode("raw_unicode_escape")

    return False


@CLIENT.event
async def on_raw_reaction_add(payload):
    print(payload)
    guild = CLIENT.get_guild(payload.guild_id)
    for channel_config in config.CHANNELS:
        if should_manage_from_reaction_emoji(channel_config, payload):
            print(channel_config)
            target_channel = guild.get_channel(channel_config["channel_id"])

            current_permissions = target_channel.permissions_for(payload.member)

            await target_channel.set_permissions(
                payload.member,
                reason="Emoji React",
                read_messages=not current_permissions.read_messages,
            )
            message_channel = guild.get_channel(payload.channel_id)
            message = await message_channel.fetch_message(payload.message_id)
            await message.remove_reaction(payload.emoji, payload.member)


@CLIENT.command()
@commands.has_permissions(manage_channels=True)
@commands.check(in_managed_channnel)
async def add(ctx, *, member):
    found = None
    for guild_member in ctx.guild.members:
        if guild_member.mentioned_in(ctx.message):
            found = guild_member

    if not found:
        await ctx.send(f"Couldn't find `{member}` in guild.")
        return

    channel = ctx.message.channel
    message_link = (
        f"https://discord.com/channels/{ctx.guild.id}/{channel.id}/{ctx.message.id}"
    )
    await channel.set_permissions(found, reason=message_link, read_messages=True)
    await ctx.send(f"Done.")

@CLIENT.command()
@commands.has_permissions(manage_channels=True)
async def report(ctx, *, member):
    found = None
    for guild_member in ctx.guild.members:
        if guild_member.mentioned_in(ctx.message):
            found = guild_member

    if not found:
        await ctx.send(f"Couldn't find `{member}` in guild.")
        return

    print([r for r in ctx.guild.roles if r.name == "quarantined"][0])
    channel = ctx.message.channel
    await channel.set_permissions(
                found,
                reason=f"Reported by {ctx.author.name}#{ctx.author.discriminator}",
                read_messages=False,
            )
    await found.edit( reason=f"Reported by {ctx.author.name}#{ctx.author.discriminator}", roles=[r for r in ctx.guild.roles if r.name == "quarantined"])

    await ctx.send(f"{found.mention} has been reported by {ctx.author.mention} — CC <@&315339680641974273>")

@CLIENT.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.CheckFailure):
        print(
            f"Check condition failed. Command: '{ctx.command}', Channel: '{ctx.channel}', Channel ID: '{ctx.channel.id}'"
        )
    else:
        print(f"Ignoring exception in command {ctx.command}:", file=sys.stderr)
        traceback.print_exception(
            type(error), error, error.__traceback__, file=sys.stderr
        )


if __name__ == "__main__":
    CLIENT.run(config.DISCORD_TOKEN)
