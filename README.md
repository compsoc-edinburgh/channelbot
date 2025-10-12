# channelbot

The role/channel opt-in selection works in two components: the messages themselves and the bot.

## The messages themselves

The message part is really a single-run script that sends/edits messages in #readme of the CompSoc Discord server and creates pretty buttons.

These can be edited through the XML files under `messages/`. This will trigger a GitHub Action [workflow](https://github.com/compsoc-edinburgh/channelbot/blob/main/.github/workflows/update-discord-messages.yaml) that has the destination message IDs hardcoded, and will set up the buttons and embeds. It will also update the Last Updated timestamp on the embeds.

Edit the XML if you want to add a new button, change the embeds, or change what buttons do.

If you want to add a new embed message altogether, you have to also edit the GitHub Action workflow on top of creating a new XML file. You'll need to run the action once without a destination message ID to create a new message, then afterwards hardcode the message ID.

## The Discord bot 

The bot listens for click events on the buttons, reads its ID to decide on what to do, and actions them. The action can be toggling a role or toggling access to an opt-in channel. 

Edit the bot if you want to change the bot's functionality, add more capabilities, or other things. You may want to clone and run locally to test. Pushing to GitHub will build an image and push it to ghcr.

This is now hosted in the [CompSoc k8s cluster](https://github.com/compsoc-edinburgh/CompSoc-k8s/tree/master/services/channelbot).

