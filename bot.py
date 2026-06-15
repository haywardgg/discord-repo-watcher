#!/usr/bin/env python3
"""
Discord Repo Watcher Bot
Listens for commands and periodically checks watched repos for new commits.
"""

import asyncio
import logging
import logging.handlers
import os
import signal
import sys

import discord
from discord.ext import commands, tasks

import config
import repo_manager
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
    repo_manager.save_repos(repo_list_path, [])


# ── Events ────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    logger.info("Bot is ready! Logged in as %s (ID: %s)", bot.user, bot.user.id)
    logger.info("Watched repo list: %s", repo_list_path)
    repos = repo_manager.load_repos(repo_list_path)
    logger.info("Currently tracking %d repo(s)", len(repos))
    check_loop.start()


# ── Notification Helper ───────────────────────────────────────────────────────

COMMIT_EMBED_COLOR = 5814783  # A soft green


async def send_commit_notification(
    channel: discord.TextChannel,
    repo: str,
    commit_hash: str,
    commit_msg: str,
    author: str,
    commit_date: str,
    commit_url: str,
) -> bool:
    """
    Send a rich embed about a new commit to the given channel.
    Returns True on success.
    """
    description = f"**Repository:** {repo}\n**Author:** {author}"
    if len(description) > 2048:
        description = description[:2045] + "..."

    embed = discord.Embed(
        title="📦 New Commit Detected",
        description=description,
        url=f"https://github.com/{repo}",
        color=COMMIT_EMBED_COLOR,
        timestamp=discord.utils.parse_time(commit_date) if commit_date else discord.utils.utcnow(),
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
    embed.set_thumbnail(url="https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png")

    await channel.send(embed=embed)
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
                        f"First seen commit: {commit_hash[:7]}"
                    )
                    await send_commit_notification(
                        notification_channel, repo, commit_hash,
                        commit_msg, author, commit_date, commit_url,
                    )
                elif reason == "new_commit":
                    if await send_commit_notification(
                        notification_channel, repo, commit_hash,
                        commit_msg, author, commit_date, commit_url,
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


@check_loop.before_loop
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
async def add_repo(ctx: commands.Context, *, repo: str):
    """Add a repository to watch. Usage: !add-repo owner/repo-name"""
    await _delete_command(ctx)
    try:
        added = repo_manager.add_repo(repo_list_path, repo)
        if added:
            await ctx.send(f"✅ **{repo}** has been added to the watch list.", delete_after=30)
            logger.info("User %s added repo: %s", ctx.author, repo)
        else:
            await ctx.send(f"⚠️ **{repo}** is already in the watch list.", delete_after=30)
    except ValueError as e:
        await ctx.send(f"❌ {e}", delete_after=30)


@bot.command(name="remove-repo", aliases=["remove", "rm"])
async def remove_repo(ctx: commands.Context, *, repo: str):
    """Remove a repository from the watch list. Usage: !remove-repo owner/repo-name"""
    await _delete_command(ctx)
    removed = repo_manager.remove_repo(repo_list_path, repo)
    if removed:
        await ctx.send(f"✅ **{repo}** has been removed from the watch list.", delete_after=30)
        logger.info("User %s removed repo: %s", ctx.author, repo)
    else:
        await ctx.send(f"⚠️ **{repo}** was not found in the watch list.", delete_after=30)


@bot.command(name="list-repos", aliases=["list", "repos"])
async def list_repos(ctx: commands.Context):
    """List all currently watched repositories."""
    await _delete_command(ctx)
    repos = repo_manager.load_repos(repo_list_path)
    if not repos:
        await ctx.send("📭 No repositories are being watched. Use `!add-repo <owner/repo>` to add one.", delete_after=30)
        return

    lines = "\n".join(f"• `{r}`" for r in repos)
    await ctx.send(f"**📋 Watched Repositories ({len(repos)}):**\n{lines}", delete_after=60)


@bot.command(name="check-now", aliases=["check", "scan"])
async def check_now(ctx: commands.Context):
    """Manually check all watched repositories for new commits now."""
    await _delete_command(ctx)
    repos = repo_manager.load_repos(repo_list_path)
    if not repos:
        await ctx.send("📭 No repositories to check.", delete_after=30)
        return

    await ctx.send(f"🔍 Checking {len(repos)} repo(s)... This may take a moment.", delete_after=120)

    errors = 0
    updates = 0
    for repo in repos:
        try:
            result = watcher.check_repo(repo)
            has_update = result[0]

            if not has_update and result[1] is not None:
                error_msg = result[1]
                logger.warning("Error checking %s: %s", repo, error_msg)
                await ctx.send(f"⚠️ **{repo}** - {error_msg}", delete_after=60)
                errors += 1
            elif has_update and len(result) > 2:
                _, commit_hash, reason, commit_msg, author, commit_date, commit_url = result
                if reason == "first_seen":
                    await ctx.send(
                        f"⚠️ **{repo}** - Now tracking! First seen commit: {commit_hash[:7]}",
                        delete_after=60,
                    )
                    await send_commit_notification(
                        ctx.channel, repo, commit_hash,
                        commit_msg, author, commit_date, commit_url,
                    )
                    updates += 1
                elif reason == "new_commit":
                    await send_commit_notification(
                        ctx.channel, repo, commit_hash,
                        commit_msg, author, commit_date, commit_url,
                    )
                    watcher.confirm_notification(repo, commit_hash)
                    updates += 1
            # else: no new commits, skip
        except Exception as e:
            logger.error("Unexpected error checking %s: %s", repo, e, exc_info=True)
            errors += 1

        await asyncio.sleep(1)

    summary = f"✅ Scan complete. {updates} update(s) sent, {errors} error(s)."
    await ctx.send(summary, delete_after=60)


@bot.command(name="help", aliases=["commands"])
async def help_command(ctx: commands.Context):
    """Show available commands."""
    await _delete_command(ctx)
    embed = discord.Embed(
        title="🤖 GitHub Repo Watcher Commands",
        color=COMMIT_EMBED_COLOR,
    )
    embed.add_field(
        name="!add-repo <owner/repo>",
        value="Add a repository to watch.\n*Alias: !add*",
        inline=False,
    )
    embed.add_field(
        name="!remove-repo <owner/repo>",
        value="Remove a repository from the watch list.\n*Aliases: !remove, !rm*",
        inline=False,
    )
    embed.add_field(
        name="!list-repos",
        value="List all currently watched repositories.\n*Aliases: !list, !repos*",
        inline=False,
    )
    embed.add_field(
        name="!check-now",
        value="Manually check all repos for new commits right now.\n*Aliases: !check, !scan*",
        inline=False,
    )
    embed.add_field(
        name="!help",
        value="Show this help message.\n*Aliases: !commands*",
        inline=False,
    )
    await ctx.send(embed=embed, delete_after=120)


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