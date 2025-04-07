import os
import asyncio
from datetime import datetime

import openai
from dotenv import load_dotenv

# atproto libs
from atproto import AsyncClient, models
from atproto.subscriptions.repos import (
    AsyncSubscribeRepos, 
    parse_subscribe_repos_message
)

load_dotenv()

# Set your OpenAI key
openai.api_key = os.getenv("OPENAI_API_KEY")

# Initialize Bluesky client
bluesky_client = AsyncClient()

SYSTEM_PROMPT = """You are a helpful assistant on Bluesky. When users mention you, they might be:
    1. Asking a general question
    2. Asking about a specific post (when their mention is a reply to another post)
    3. Requesting help to draft a reply to a post

    Respond concisely (under 300 characters) and helpfully. If referring to a post, mention that you're responding to it."""

async def generate_llm_reply(context: str, query: str) -> str:
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # or gpt-4 if you have access
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{context}\n\nUser's request: {query}"}
            ],
            max_tokens=200
        )
        content = response.choices[0].message.content.strip()
        return content[:280]  # short enough for Bluesky
    except Exception as e:
        print(f"[OpenAI Error]: {e}")
        return "Sorry, I'm having trouble responding right now!"

async def handle_post(
    record: models.AppBskyFeedPost.Record,
    repo_did: str,
    bot_did: str,
    bot_handle: str
):
    # Check if we are mentioned
    mentioned = False
    if record.facets:
        for facet in record.facets:
            for feature in facet.features:
                if (isinstance(feature, models.AppBskyRichtextFacet.Mention) and 
                    feature.did == bot_did):
                    mentioned = True
                    break
            if mentioned:
                break

    if not mentioned:
        return  # do nothing if we weren't mentioned

    print(f"New mention from: {repo_did}, text={record.text}")

    # Fetch parent context if it's a reply
    context = ""
    if record.reply and record.reply.parent.uri:
        try:
            thread_res = await bluesky_client.app.bsky.feed.get_post_thread(
                {"uri": record.reply.parent.uri}
            )
            if hasattr(thread_res.thread.post, "record"):
                parent_text = getattr(thread_res.thread.post.record, "text", "")
                context = f"Post being discussed:\n{parent_text}"
        except Exception as e:
            print(f"Couldn't fetch parent post: {e}")

    # Remove bot handle from the user text
    query = record.text.replace(f"@{bot_handle}", "").strip()

    # Generate LLM reply
    reply_text = await generate_llm_reply(context, query)

    # Build reference for the same conversation
    reply_ref = models.AppBskyFeedPost.ReplyRef(
        parent=models.ComAtprotoRepoStrongRef.Main(
            uri=record.uri,
            cid=record.cid
        ),
        root=models.ComAtprotoRepoStrongRef.Main(
            uri=(record.reply.root.uri if record.reply else record.uri),
            cid=(record.reply.root.cid if record.reply else record.cid)
        )
    )

    try:
        # Post the reply on behalf of the bot
        await bluesky_client.app.bsky.feed.post.create(
            repo=bot_did,  # The bot’s DID
            record=models.AppBskyFeedPost.Record(
                text=reply_text,
                createdAt=datetime.utcnow().isoformat(),
                reply=reply_ref
            )
        )
        print(f"Posted response: {reply_text}")
    except Exception as e:
        print(f"Failed to post response: {e}")

async def main():
    # 1) Login
    await bluesky_client.login(
        os.getenv('BLUESKY_HANDLE'),
        os.getenv('BLUESKY_APP_PASSWORD')
    )

    # Fetch the bot's DID & handle
    bot_profile = await bluesky_client.app.bsky.actor.get_profile(
        {"actor": os.getenv("BLUESKY_HANDLE")}
    )
    bot_did = bot_profile.did
    bot_handle = bot_profile.handle

    # 2) Subscribe to repos
    subscription_client = AsyncSubscribeRepos()

    async for raw_msg in subscription_client:
        parsed = parse_subscribe_repos_message(raw_msg)
        if isinstance(parsed, models.ComAtprotoSyncSubscribeRepos.Commit):
            # Each commit can have multiple operations
            repo_did = parsed.repo  # DID of the poster
            for op in parsed.ops:
                if op.action == "create" and op.value is not None:
                    # Check if it's a feed.post
                    if op.value.get("$type") == "app.bsky.feed.post":
                        try:
                            record = models.AppBskyFeedPost.Record(**op.value)
                            await handle_post(record, repo_did, bot_did, bot_handle)
                        except Exception as e:
                            print(f"Error constructing record: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped gracefully")