#!/usr/bin/env python3
"""
Discord Repo Watcher Bot
Listens for commands and periodically checks watched repos for new commits.
"""

import asyncio
import logging
import logging.handlers
import os
import sys

import discord
from discord.ext import commands, tasks

import config
import notification_tracker
import repo_manager
import state_manager
import watcher

# ── Logging Setup ──────────────────────────────────────────────────────────────

log_file = config.get_log_file_path()
log_dir = os.path.dirname(log_file)
if log_dir:
    os.makedirs(log_dir, exist_ok=True)

logger = logging.getLogger("repo_watcher")
logger.setLevel(logging.DEBUG)

# File handler (rotating, 5MB per file, keep 3 backups)
file_handler = logging.handlers.RotatingFileHandler(
    log_file, maxBytes=5_242_880, backupCount=3, encoding="utf-8"
)
file_handler.setLevel(logging.DEBUG)
file_format = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
file_handler.setFormatter(file_format)
logger.addHandler(file_handler)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_format = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
console_handler.setFormatter(console_format)
logger.addHandler(console_handler)

# ── Bot Setup ──────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Required for on_member_remove event (leave cleanup)

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    description="GitHub Repo Watcher - monitors repos and notifies on new commits",
    help_command=None,  # Disable built-in help so we can register our own
)

# Ensure data files exist
repo_list_path = config.get_repo_list_path()
os.makedirs(os.path.dirname(repo_list_path) or ".", exist_ok=True)
if not os.path.isfile(repo_list_path):
    repo_manager.save_repos(repo_list_path, {})


# ── Permission Check ──────────────────────────────────────────────────────────


def is_admin_or_mod():
    """
    Check decorator that only allows server admins (Administrator permission)
    or moderators (Manage Messages permission) to run a command.
    """
    async def predicate(ctx: commands.Context) -> bool:
        # Allow bot owners unconditionally
        if ctx.author.id == ctx.bot.owner_id:
            return True

        # Check the author's permissions in the current channel
        permissions = ctx.author.guild_permissions if isinstance(ctx.author, discord.Member) else discord.Permissions()

        # Administrators have full control
        if permissions.administrator:
            return True

        # Moderators typically have at least one of these permissions
        if permissions.manage_guild or permissions.manage_messages or permissions.kick_members or permissions.ban_members:
            return True

        # If none of the above, deny access
        raise commands.MissingPermissions(
            ["administrator", "manage_guild", "manage_messages", "kick_members", "ban_members"]
        )
    return commands.check(predicate)


def is_admin_or_mod_or_member():
    """
    Check decorator for !add-repo:
    - Server admins and moderators: always allowed
    - Regular members: allowed if joined the server more than 24 hours ago
    - Otherwise: denied with a message explaining the 24-hour wait
    """
    async def predicate(ctx: commands.Context) -> bool:
        # Allow bot owners unconditionally
        if ctx.author.id == ctx.bot.owner_id:
            return True

        # Admins and moderators always allowed
        if isinstance(ctx.author, discord.Member):
            permissions = ctx.author.guild_permissions
            if permissions.administrator:
                return True
            if permissions.manage_guild or permissions.manage_messages or permissions.kick_members or permissions.ban_members:
                return True

            # Regular member — check server join age
            if ctx.author.joined_at is None:
                raise commands.CheckFailure(
                    "⏳ Unable to verify your server join date. "
                    "Please try again later or ask an admin/moderator for help."
                )
            now = discord.utils.utcnow()
            member_age = now - ctx.author.joined_at
            if member_age.total_seconds() >= 86_400:  # 24 hours
                return True

            # Too new — raise a specific error
            raise commands.CheckFailure(
                "⏳ You must be a member of this server for at least 24 hours before adding "
                "repositories. Please wait or ask an admin/moderator for help."
            )

        # DM channels / non-member — deny
        raise commands.MissingPermissions(
            ["administrator", "manage_guild", "manage_messages", "kick_members", "ban_members"]
        )
    return commands.check(predicate)


# ── Events ────────────────────────────────────────────────────────────────────

# Strict command channel — if configured, silently delete any non-command
# message in the specified channel.
_strict_channel = config.get_strict_command_channel().lower()


@bot.event
async def on_message(message: discord.Message) -> None:
    """Silently delete non-command messages in the strict command channel."""
    # Always process commands first
    await bot.process_commands(message)

    # Skip if strict channel not configured
    if not _strict_channel:
        return

    # Only act in the configured channel
    if not isinstance(message.channel, discord.TextChannel) or message.channel.name.lower() != _strict_channel:
        return

    # Skip bot messages
    if message.author.bot:
        return

    # If this message triggered a command (prefix match), leave it — on_command will delete it
    ctx = await bot.get_context(message)
    if ctx.valid:
        return

    # Silently delete the non-command message
    try:
        await message.delete()
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        pass


@bot.event
async def on_member_remove(member: discord.Member) -> None:
    """When a member leaves, remove all repos they added and their commit embeds."""
    state_file = config.get_state_file_path()
    tracker_path = config.get_notification_tracking_path()
    repos_with_owners = repo_manager.load_repos_with_owners(repo_list_path)
    removed: list[str] = []
    embed_deleted_count = 0
    for repo, owner_id in list(repos_with_owners.items()):
        if owner_id == member.id:
            del repos_with_owners[repo]
            state_manager.remove_repo(state_file, repo)
            removed.append(repo)
            # Try to delete the commit notification embed from the channel
            tracked = notification_tracker.get_notification_message(tracker_path, repo)
            if tracked:
                channel_id, message_id = tracked
                guild = member.guild
                channel = guild.get_channel(channel_id) if guild else None
                if channel and isinstance(channel, discord.TextChannel):
                    try:
                        msg = await channel.fetch_message(message_id)
                        await msg.delete()
                        embed_deleted_count += 1
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        pass
                notification_tracker.remove_notification_message(tracker_path, repo)
    if removed:
        repo_manager.save_repos(repo_list_path, repos_with_owners)
        logger.info(
            "Member %s (ID: %d) left — removed %d repo(s), deleted %d embed(s): %s",
            member, member.id, len(removed), embed_deleted_count, ", ".join(removed),
        )
        # Post a light-hearted announcement in the repo-watcher channel
        repo_list = "\n".join(f"• `{r}`" for r in removed)
        channel_msgs = [
            f"👋 **{member.display_name}** has left the building… and taken their toys with them!",
            f"🧹 Cleanup crew reporting in — **{member.display_name}** dipped, so we yeeted their {len(removed)} repo(s):",
            f"🚪 **{member.display_name}** ghosted us. Their {len(removed)} repo(s) have been escorted out.",
            f"🛸 **{member.display_name}** beamed up. Repo scanner disengaged. {len(removed)} repo(s) removed from watch.",
            f"💨 **{member.display_name}** vanished into thin air. Their watch list contributions have been respectfully retired.",
        ]
        import random
        channel_text = f"{random.choice(channel_msgs)}\n{repo_list}"
        announce_channel = _find_notification_channel()
        if announce_channel:
            try:
                msg = await announce_channel.send(channel_text)
                await msg.delete(delay=60)
            except (discord.Forbidden, discord.HTTPException):
                pass
        # DM the server owner
        guild_owner = member.guild.owner
        if guild_owner and guild_owner.id != member.id:
            try:
                await guild_owner.send(
                    f"📋 **Member Left — Repo Cleanup**\n"
                    f"**{member.display_name}** (ID: `{member.id}`) has left the server.\n"
                    f"Their {len(removed)} repository(ies) have been removed from the watch list "
                    f"and {embed_deleted_count} commit embed(s) deleted:\n"
                    + "\n".join(f"• `{r}`" for r in removed)
                )
            except (discord.Forbidden, discord.HTTPException):
                pass


@bot.event
async def on_ready():
    assert bot.user is not None, "bot.user is None in on_ready"
    logger.info("Bot is ready! Logged in as %s (ID: %s)", bot.user, bot.user.id)
    logger.info("Watched repo list: %s", repo_list_path)
    repos = repo_manager.load_repos(repo_list_path)
    logger.info("Currently tracking %d repo(s)", len(repos))
    check_loop.start()  # type: ignore[attr-defined]


# ── Notification Helper ───────────────────────────────────────────────────────

COMMIT_EMBED_COLOR = 5814783  # A soft green


async def send_commit_notification(
    channel: discord.abc.Messageable,
    repo: str,
    commit_hash: str,
    commit_msg: str,
    author: str,
    commit_date: str,
    commit_url: str,
    avatar_url: str | None = None,
) -> discord.Message | None:
    """
    Send a rich embed about a new commit to the given channel.
    Uses the repository owner's avatar as the embed thumbnail
    if available, otherwise falls back to the generic GitHub logo.
    Returns the sent Message on success, None on failure.
    """
    description = f"**Repository:** {repo}\n**Author:** {author}"
    if len(description) > 2048:
        description = description[:2045] + "..."

    # Parse the commit timestamp safely
    try:
        embed_timestamp = discord.utils.parse_time(commit_date) if commit_date else discord.utils.utcnow()
    except (ValueError, TypeError, Exception):
        embed_timestamp = discord.utils.utcnow()

    embed = discord.Embed(
        title="📦 New Commit Detected",
        description=description,
        url=f"https://github.com/{repo}",
        color=COMMIT_EMBED_COLOR,
        timestamp=embed_timestamp,
    )
    embed.add_field(
        name="📝 Commit",
        value=f"[{commit_hash[:7]}]({commit_url})",
        inline=True,
    )
    embed.add_field(
        name="💬 Message",
        value=commit_msg[:1024] if commit_msg else "*No message*",
        inline=False,
    )
    embed.set_footer(text="GitHub Repo Watcher")

    # Use repo owner's avatar if available, otherwise fall back to the generic GitHub logo
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)
    else:
        embed.set_thumbnail(url="https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png")

    message = await channel.send(embed=embed)
    return message


async def _handle_commit_update(
    channel: discord.abc.Messageable,
    repo: str,
    commit_hash: str,
    commit_msg: str,
    author: str,
    commit_date: str,
    commit_url: str,
    avatar_url: str | None = None,
) -> bool:
    """
    Send a commit notification, optionally deleting the previous one for this repo.

    If DELETE_PREVIOUS_NOTIFICATIONS is enabled, deletes the old notification
    message before sending the new one, so there is only ever one embed per repo.

    Returns True on success.
    """
    # If deletion is enabled, try to remove the previous notification
    if config.get_delete_previous_notifications():
        tracker_path = config.get_notification_tracking_path()
        previous = notification_tracker.get_notification_message(tracker_path, repo)
        if previous:
            prev_channel_id, prev_message_id = previous
            try:
                guild = getattr(channel, "guild", None)
                prev_channel = guild.get_channel(prev_channel_id) if guild else bot.get_channel(prev_channel_id)
                if prev_channel and isinstance(prev_channel, discord.TextChannel):
                    prev_message = await prev_channel.fetch_message(prev_message_id)
                    await prev_message.delete()
                    logger.debug("Deleted previous notification for %s (msg %d)", repo, prev_message_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException, Exception) as e:
                logger.debug("Could not delete previous notification for %s: %s", repo, e)

    # Send the new notification
    message = await send_commit_notification(
        channel, repo, commit_hash,
        commit_msg, author, commit_date, commit_url,
        avatar_url=avatar_url,
    )
    if message is None:
        return False

    # Track the new message if deletion is enabled
    if config.get_delete_previous_notifications():
        tracker_path = config.get_notification_tracking_path()
        notification_tracker.set_notification_message(
            tracker_path, repo, message.channel.id, message.id
        )

    return True


# ── Background Check Loop ─────────────────────────────────────────────────────

@tasks.loop(seconds=config.get_check_interval())
async def check_loop():
    """Periodically check all watched repos for new commits."""
    repos = repo_manager.load_repos(repo_list_path)
    if not repos:
        logger.debug("No repos to check")
        return

    logger.info("========== Checking %d repo(s) ==========", len(repos))

    # Find the first channel the bot can see to send notifications
    notification_channel = _find_notification_channel()
    if not notification_channel:
        logger.warning("No accessible text channel found to send notifications")
        return

    errors = 0
    for repo in repos:
        try:
            result = watcher.check_repo(repo)
            has_update = result[0]

            if not has_update and result[1] is not None:
                # Error case: (False, error_message)
                error_msg = result[1]
                logger.warning("Error checking %s: %s", repo, error_msg)
                await notification_channel.send(
                    f"⚠️ **{repo}** - {error_msg}"
                )
                errors += 1
            elif has_update and len(result) > 2:
                # Update case: (True, hash, reason, msg, author, date, url)
                _, commit_hash, reason, commit_msg, author, commit_date, commit_url = result
                if reason == "first_seen":
                    await notification_channel.send(
                        f"⚠️ **{repo}** - Now tracking this repository! "
                        f"First seen commit: {commit_hash[:7]}",
                        delete_after=10,
                    )
                    avatar_url = watcher.get_repo_avatar_url(repo)
                    await _handle_commit_update(
                        notification_channel, repo, commit_hash,
                        commit_msg, author, commit_date, commit_url,
                        avatar_url=avatar_url,
                    )
                elif reason == "new_commit":
                    avatar_url = watcher.get_repo_avatar_url(repo)
                    if await _handle_commit_update(
                        notification_channel, repo, commit_hash,
                        commit_msg, author, commit_date, commit_url,
                        avatar_url=avatar_url,
                    ):
                        watcher.confirm_notification(repo, commit_hash)
                    else:
                        errors += 1
            # else: (True, None) = no new commits, skip
        except Exception as e:
            logger.error("Unexpected error checking %s: %s", repo, e, exc_info=True)
            errors += 1

        await asyncio.sleep(1)  # Small delay between API calls

    logger.info("========== Scan Complete: errors=%d ==========", errors)
    if errors > 0:
        await notification_channel.send(
            f"⚠️ **System** - Scan completed with {errors} errors. Check logs for details."
        )


def _find_notification_channel() -> discord.TextChannel | None:
    """
    Find a suitable text channel to send notifications.
    Prefers channels named 'repo-watcher', 'github', 'general', or the first available.
    """
    for guild in bot.guilds:
        for channel in guild.text_channels:
            name_lower = channel.name.lower()
            if name_lower in ("repo-watcher", "repo_watcher", "github", "github-watcher"):
                return channel
    # Fallback: first text channel in first guild
    for guild in bot.guilds:
        for channel in guild.text_channels:
            return channel
    return None


@check_loop.before_loop  # type: ignore[attr-defined]
async def before_check_loop():
    """Wait until the bot is ready before starting the loop."""
    await bot.wait_until_ready()


# ── Commands ──────────────────────────────────────────────────────────────────


async def _delete_command(ctx: commands.Context) -> None:
    """Delete the user's command message. Silently ignores permission errors."""
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.HTTPException):
        pass


@bot.command(name="add-repo", aliases=["add"])
@is_admin_or_mod_or_member()
async def add_repo(ctx: commands.Context, *, repo: str):
    """Add a repository to watch. Usage: !add-repo owner/repo-name"""
    await _delete_command(ctx)
    # Reject URLs — users must use owner/repo format to avoid Discord timeout penalties
    repo_stripped = repo.strip()
    if "://" in repo_stripped or repo_stripped.startswith(("github.com/", "www.github.com/")):
        await ctx.send(
            f"❌ Please use the short format: `owner/repo` (not a URL).\n"
            f"Example: `microsoft/vscode` instead of `{repo_stripped}`", delete_after=10
        )
        return
    # Clean and validate format
    cleaned = repo_manager.clean_repo(repo)
    if not cleaned or "/" not in cleaned:
        await ctx.send(
            f"❌ Invalid repository format: '{repo}'. Use `owner/repo` format.", delete_after=10
        )
        return
    # Check if already in the list
    current = repo_manager.load_repos(repo_list_path)
    if cleaned in current:
        await ctx.send(f"⚠️ **{cleaned}** is already in the watch list.", delete_after=10)
        return
    # Verify the repo exists on GitHub
    await ctx.send(f"🔍 Verifying **{cleaned}** exists on GitHub...", delete_after=10)
    if not watcher.repo_exists(cleaned):
        await ctx.send(
            f"❌ **{cleaned}** does not exist or is not accessible on GitHub. "
            "Check the spelling and ensure it's a public repository.",
            delete_after=10,
        )
        return
    # Add it with the user's ID for ownership tracking
    try:
        added = repo_manager.add_repo(repo_list_path, cleaned, ctx.author.id)
        if added:
            await ctx.send(f"✅ **{cleaned}** has been added to the watch list.", delete_after=10)
            logger.info("User %s added repo: %s", ctx.author, cleaned)
        else:
            await ctx.send(f"⚠️ **{cleaned}** is already in the watch list.", delete_after=10)
    except ValueError as e:
        await ctx.send(f"❌ {e}", delete_after=10)


@bot.command(name="remove-repo", aliases=["remove", "rm"])
async def remove_repo(ctx: commands.Context, *, repo: str):
    """Remove a repository from the watch list. Usage: !remove-repo owner/repo-name"""
    await _delete_command(ctx)
    cleaned = repo_manager.clean_repo(repo)
    if not cleaned or "/" not in cleaned:
        await ctx.send(
            f"❌ Invalid repository format: '{repo}'. Use `owner/repo` format.", delete_after=10
        )
        return

    # Check if repo exists
    if cleaned not in repo_manager.load_repos(repo_list_path):
        await ctx.send(f"⚠️ **{cleaned}** was not found in the watch list.", delete_after=10)
        return

    # Permission logic: bot owner, admins, and mods can remove any repo
    is_admin = False
    if ctx.author.id == ctx.bot.owner_id:
        is_admin = True
    elif isinstance(ctx.author, discord.Member):
        perms = ctx.author.guild_permissions
        if perms.administrator or perms.manage_guild or perms.manage_messages or perms.kick_members or perms.ban_members:
            is_admin = True

    if not is_admin:
        # Regular member — check ownership
        repo_owner = repo_manager.get_repo_owner(repo_list_path, cleaned)
        if repo_owner is None:
            await ctx.send(
                f"❌ **{cleaned}** has no recorded owner. Only admins/moderators can remove it.",
                delete_after=10,
            )
            return
        if repo_owner != ctx.author.id:
            await ctx.send(
                f"❌ You can only remove repositories you added yourself. "
                f"**{cleaned}** was added by <@{repo_owner}>. Ask them or an admin/moderator to remove it.",
                delete_after=10,
            )
            return

    # Remove it
    removed = repo_manager.remove_repo(repo_list_path, cleaned)
    if removed:
        await ctx.send(f"✅ **{cleaned}** has been removed from the watch list.", delete_after=10)
        logger.info("User %s removed repo: %s", ctx.author, cleaned)
    else:
        await ctx.send(f"⚠️ **{cleaned}** was not found in the watch list.", delete_after=10)


@bot.command(name="list-repos", aliases=["list", "repos"])
async def list_repos(ctx: commands.Context):
    """List all currently watched repositories (sent via DM)."""
    await _delete_command(ctx)
    repos = repo_manager.load_repos(repo_list_path)
    if not repos:
        await ctx.send("📭 No repositories are being watched. Use `!add-repo <owner/repo>` to add one.", delete_after=10)
        return

    lines = "\n".join(f"• `{r}`" for r in repos)
    content = f"**📋 Watched Repositories ({len(repos)}):**\n{lines}"
    try:
        await ctx.author.send(content)
        await ctx.send("📬 Sent — check your DMs!", delete_after=5)
    except (discord.Forbidden, discord.HTTPException):
        await ctx.send(content, delete_after=30)


@bot.command(name="check-now", aliases=["check", "scan"])
@is_admin_or_mod()
async def check_now(ctx: commands.Context):
    """Manually check all watched repositories for new commits now."""
    await _delete_command(ctx)
    repos = repo_manager.load_repos(repo_list_path)
    if not repos:
        await ctx.send("📭 No repositories to check.", delete_after=10)
        return

    await ctx.send(f"🔍 Checking {len(repos)} repo(s)... This may take a moment.", delete_after=10)

    errors = 0
    updates = 0
    for repo in repos:
        try:
            result = watcher.check_repo(repo)
            has_update = result[0]

            if not has_update and result[1] is not None:
                error_msg = result[1]
                logger.warning("Error checking %s: %s", repo, error_msg)
                await ctx.send(f"⚠️ **{repo}** - {error_msg}", delete_after=10)
                errors += 1
            elif has_update and len(result) > 2:
                _, commit_hash, reason, commit_msg, author, commit_date, commit_url = result
                if reason == "first_seen":
                    await ctx.send(
                        f"⚠️ **{repo}** - Now tracking! First seen commit: {commit_hash[:7]}",
                        delete_after=10,
                    )
                    avatar_url = watcher.get_repo_avatar_url(repo)
                    await _handle_commit_update(
                        ctx.channel, repo, commit_hash,
                        commit_msg, author, commit_date, commit_url,
                        avatar_url=avatar_url,
                    )
                    updates += 1
                elif reason == "new_commit":
                    avatar_url = watcher.get_repo_avatar_url(repo)
                    await _handle_commit_update(
                        ctx.channel, repo, commit_hash,
                        commit_msg, author, commit_date, commit_url,
                        avatar_url=avatar_url,
                    )
                    watcher.confirm_notification(repo, commit_hash)
                    updates += 1
            # else: no new commits, skip
        except Exception as e:
            logger.error("Unexpected error checking %s: %s", repo, e, exc_info=True)
            errors += 1

        await asyncio.sleep(1)

    summary = f"✅ Scan complete. {updates} update(s) sent, {errors} error(s)."
    await ctx.send(summary, delete_after=10)


# ── Help Command ──────────────────────────────────────────────────────────────

# The help command is registered via a function so it can use the configured name
# from .env. Set HELP_COMMAND in your .env file (e.g. HELP_COMMAND="repos-help")
# to avoid conflicts with other bots responding to !help.


def _register_help_command():
    """Register the help command with the configured name from .env."""
    help_name = config.get_help_command()

    @bot.command(name=help_name, aliases=["commands"])
    async def help_command(ctx: commands.Context):
        """Show available commands."""
        await _delete_command(ctx)
        prefix = ctx.prefix
        embed = discord.Embed(
            title="🤖 GitHub Repo Watcher Commands",
            color=COMMIT_EMBED_COLOR,
        )
        embed.add_field(
            name=f"{prefix}add-repo <owner/repo>",
            value=f"Add a repository to watch.\n*Alias: {prefix}add*\n*Admins, Mods, or members (24h+)*\nRepository is verified before adding.",
            inline=False,
        )
        embed.add_field(
            name=f"{prefix}remove-repo <owner/repo>",
            value=f"Remove a repository from the watch list.\n*Aliases: {prefix}remove, {prefix}rm*\n*Admins/Mods can remove any; members can remove their own*",
            inline=False,
        )
        embed.add_field(
            name=f"{prefix}list-repos",
            value=f"List all currently watched repositories.\n*Aliases: {prefix}list, {prefix}repos*",
            inline=False,
        )
        embed.add_field(
            name=f"{prefix}check-now",
            value=f"Manually check all repos for new commits right now.\n*Aliases: {prefix}check, {prefix}scan*\n*Restricted to Admins & Moderators*",
            inline=False,
        )
        embed.add_field(
            name=f"{prefix}{help_name}",
            value=f"Show this help message.\n*Aliases: {prefix}commands*",
            inline=False,
        )
        try:
            await ctx.author.send(embed=embed)
            await ctx.send("📬 Sent — check your DMs!", delete_after=5)
        except (discord.Forbidden, discord.HTTPException):
            await ctx.send(embed=embed, delete_after=30)


_register_help_command()


# ── Error Handling ────────────────────────────────────────────────────────────


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    """Global error handler for command errors."""
    # Ignore command not found errors (let them pass silently)
    if isinstance(error, commands.CommandNotFound):
        return

    # Handle permission errors with a friendly message
    if isinstance(error, commands.MissingPermissions):
        await _delete_command(ctx)
        await ctx.send(
            "❌ You don't have permission to use this command. "
            "Only server admins and moderators can use it.",
            delete_after=10,
        )
        logger.warning(
            "User %s tried to use %s without permission: %s",
            ctx.author, ctx.command, error,
        )
        return

    # Handle 24-hour member gate for !add-repo
    if isinstance(error, commands.CheckFailure):
        await _delete_command(ctx)
        await ctx.send(str(error), delete_after=10)
        logger.info(
            "User %s blocked by CheckFailure on %s: %s",
            ctx.author, ctx.command, error,
        )
        return

    # Log other errors
    logger.error("Command error in %s: %s", ctx.command, error, exc_info=True)
    await ctx.send("❌ An unexpected error occurred.", delete_after=10)


# ── Main Entry Point ──────────────────────────────────────────────────────────

def main():
    """Start the bot."""
    token = config.get_bot_token()
    if not token:
        logger.error("DISCORD_BOT_TOKEN is not set. Cannot start.")
        sys.exit(1)

    logger.info("Starting Discord Repo Watcher Bot...")
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()