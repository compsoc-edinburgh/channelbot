#!/usr/bin/env python3
import sys
import traceback
import random
import re
import requests
from typing import List, Optional
import xml.etree.ElementTree as ElementTree

import discord
from discord.ext import commands

import secrets as config

bot_intents = discord.Intents.default()
bot_intents.members = True
bot_intents.message_content = True

bot = commands.Bot(command_prefix=commands.when_mentioned_or("§"), intents=bot_intents)

def construct_filename_from_custom_id(custom_id: str) -> str:
    """
    Find the relevant XML file from an action ID.
    Does not verify whether the file exists.
    """
    return f"messages/{custom_id.split('_')[0]}.xml"

@bot.event
async def on_ready():
    print(f"Logged in to Discord as {bot.user}")

def get_action_for_id(filename: str, custom_id: str) -> Optional[str]:
    """
    From a custom_id of an action, find the relevant <button> that triggered this
    within the XML at the path. Then, return the contents of the "action"
    attribute.

    Returns None if the button was not found, or if the button did not have an
    "action" attribute.
    """
    tree = ElementTree.parse(filename)
    message_tag = tree.getroot()
    for button_tag in message_tag.findall("./button"):
        if button_tag.attrib.get("id", None) == custom_id:
            return button_tag.attrib.get("action", None)
    return None

def get_unique_group_roles(filename: str, unique_group_name: str) -> List[int]:
    """
    Get the list of all role IDs for which there is a uniqueness constraint
    in the provided group name. Only searches within the XML at the provided
    filepath.
    """
    result: List[int] = []

    tree = ElementTree.parse(filename)
    message_tag = tree.getroot()
    for button_tag in message_tag.findall("./button"):
        action_str = button_tag.attrib.get("action", "")
        if action_str.startswith(f"toggle-role:{unique_group_name}:"):
            result.append(int(action_str.split(":")[2]))

    return result

async def perform_action(
    guild_id: Optional[int],
    interaction: discord.Interaction,
    action_str: str
):
    """
    Branch to either role-toggle or channel-toggle, and act upon them
    accordingly. End with an ephemeral message with either an error or some
    detailed success message.
    """
    if guild_id is None:
        return

    guild = bot.get_guild(guild_id)
    if guild is None or not isinstance(interaction.user, discord.Member):
        return


    if action_str.startswith("toggle-role:"):
        # Toggles a role by ID, optionally with a uniqueness constraint
        # Format: action="toggle-role:<ID>"
        #         action="toggle-role:<GROUP>:<ID>"

        if ":" in action_str[12:]:
            # There is a unique group defined, so take the third bit as the ID
            unique_group_name = action_str.split(":")[1]
            target_role_id = action_str.split(":")[2]
        else:
            # If not, take the second part as the ID
            unique_group_name = None
            target_role_id = action_str.split(":")[1]

        # Verify the role exists in our cache
        target_role = guild.get_role(int(target_role_id))
        if target_role is None:
            return

        current_roles = interaction.user.roles

        # If there was a uniqueness constraint for this role, we may need to
        # remove some roles roles in this group.
        removed_roles: List[discord.Role] = []

        # Perform the update
        if target_role in current_roles:
            await interaction.user.remove_roles(target_role, reason="Self-selected", atomic=True)
            # If we are removing a role, there are no constraint to worry about.
        else:
            await interaction.user.add_roles(target_role, reason="Self-selected", atomic=True)

            # If we are adding a role, worry about any uniqueness constraint, and
            # loop through all other roles in this group to unset them.
            if unique_group_name is not None:
                roles_in_group = get_unique_group_roles(construct_filename_from_custom_id(interaction.custom_id or ""), unique_group_name)

                # Discard the one that we just added, since we don't want to be
                # removing that
                other_roles = [
                    guild.get_role(role_id) for role_id in roles_in_group
                    if role_id != int(target_role_id)
                ]

                # Discard any roles we couldn't find, or ones that the user doesn't
                # have already. remove_roles() probably wouldn't complain if we try
                # to remove a role that a user doesn't have, but we also need to
                # keep track of what we really removed so we can put it in the
                # response notice.
                other_roles_filtered = [
                    role for role in other_roles
                    if role is not None and role in current_roles
                ]
                removed_roles.extend(other_roles_filtered)

                await interaction.user.remove_roles(*other_roles_filtered, reason="Self-selected (uniqueness constraint)", atomic=True)

        # Set the notice text
        if target_role in current_roles:
            # We previously had the target role, now no more
            notice = f"Removed {target_role.mention} from you!"
        else:
            # We did not have the target role, now we do. This means we may have
            # also removed some roles by the uniqueness constraint too.
            notice = f"Added {target_role.mention} to you!"
            if len(removed_roles) > 0:
                notice += f" (Removed {', '.join(map(lambda x: x.mention, removed_roles))} due to uniqueness constraints.)"

    elif action_str.startswith("toggle-channel:"):
        # Toggles access to a channel, without any visible roles. This does not
        # support uniqueness constraints, since querying each channel for permissions
        # would take too long to be feasible.
        # Format: action="toggle-channel:<ID>"

        target_channel = guild.get_channel(int(action_str[15:]))
        if target_channel is None:
            return

        # Use overwrites_for rather than permissions_for, since we want to query
        # the permissions listed on the channel (not the overall resolution). So
        # an admin could still "add" or "remove" themselves from the channel
        # overwrite, despite already having see-it-all access.
        current_permissions = target_channel.overwrites_for(interaction.user)

        await target_channel.set_permissions(
            target=interaction.user,
            reason="Self-selected",
            read_messages=not current_permissions.read_messages,
        )

        # Set the notice text
        if current_permissions.read_messages:
            notice = f"You can no longer read messages in #{target_channel.name}!"
        else:
            notice = f"You can now read messages in {target_channel.mention}!"
    else:
        # The XML may have had an invalid action attribute
        notice = f"Invalid action triggered. Please re-check the bot configuration."

    await interaction.response.send_message(
        content=f"{notice}",
        ephemeral=True
    )

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if not interaction.is_component():
        return

    if interaction.application_id != bot.application_id:
        print("Interaction application ID didn't match")
        return

    custom_id = interaction.custom_id
    if custom_id is None:
        print("Custom ID was None")
        return

    action = get_action_for_id(construct_filename_from_custom_id(custom_id), custom_id)
    await perform_action(interaction.guild_id, interaction, action)


@bot.command()
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
    await found.edit(
        reason=f"Reported by {ctx.author.name}#{ctx.author.discriminator}",
        roles=[r for r in ctx.guild.roles if r.name == "quarantined"],
    )

    await ctx.send(
        f"{found.mention} has been reported by {ctx.author.mention} — CC <@&315339680641974273>"
    )

@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    try:
        # Check if the message is a status check via a very simple:tm: regex
        # thx regex101.com
        if re.match(r"^(is +)?(my *ed|learn|[\/&\+])* +down( |\?|$)", message.content, re.IGNORECASE | re.MULTILINE):
            await message.channel.trigger_typing()

            # check if myed is down
            try:
                response = requests.get("https://www.myed.ed.ac.uk/myed-progressive/", timeout=5)
                # check if the status code is 200
                myed_up = response.status_code == 200
                myed_down_reason = None if myed_up else "Status: " + str(response.status_code)
            except requests.exceptions.RequestException as e:
                # some connection error e.g. name not resolved
                myed_up = False
                myed_down_reason = str(e)

            # check if learn is down
            try:
                response = requests.get("https://www.learn.ed.ac.uk/", timeout=5)
                # check if the status code is 200
                learn_up = response.status_code == 200
                learn_down_reason = None if learn_up else "Status: " + str(response.status_code)
            except requests.exceptions.RequestException as e:
                # some connection error e.g. name not resolved
                learn_up = False
                learn_down_reason = str(e)

            random_response = [
                "I can answer that!",
                "Uni Service Status",
                "Maybe I can help!",
                "May I interest you in some service status?",
            ]

            # Response with the status of the services in a nice embed
            await message.channel.send(
                embeds=[
                    discord.Embed(
                        title=random.choice(random_response),
                        description=f"Here's the current status of the University's services.\nFor accurate info, see https://alerts.is.ed.ac.uk/",
                        color=discord.Color.green() if myed_up and learn_up else discord.Color.red(),
                        fields=[
                            discord.EmbedField(
                                name="MyEd",
                                value=("✅ Up" if myed_up else f"❌ Down ({myed_down_reason})") + "\n" + "https://www.myed.ed.ac.uk/myed-progressive/",
                                inline=False,
                            ),
                            discord.EmbedField(
                                name="Learn",
                                value=("✅ Up" if learn_up else f"❌ Down ({learn_down_reason})") + "\n" + "https://www.learn.ed.ac.uk/",
                                inline=False,
                            ),
                        ]
                    )
                ],
            )
    except Exception:
        # Send any form of error message to the channel
        await message.channel.send("```" + traceback.format_exc() + "```")

@bot.event
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
    bot.run(config.DISCORD_TOKEN)
