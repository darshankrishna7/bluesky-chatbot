import os
import asyncio
from atproto import AsyncClient, models
from openai import OpenAI

# Load env VAR
BLUESKY_HANDLE = os.getenv('BLUESKY_HANDLE')
BLUESKY_APP_PASSWORD = os.getenv('BLUESKY_APP_PASSWORD')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Init clients
bluesky_client = AsyncClient()
openAI_client = OpenAI(api_key=OPENAI_API_KEY)

async def main():
    await bluesky_client.login(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)

    # Get bot's DID
    bot_profile = await bluesky_client.get_profile(BLUESKY_HANDLE)
    bot_did = bot_profile.did
    bot_handle = BLUESKY_HANDLE

    # System prompt for OpenAI
    SYSTEM_PROMPT = """You are a helpful assistant on Bluesky. When users mention you, they might be:
        1. Asking a general question
        2. Asking about a specific post (when their mention is a reply to another post)
        3. Requesting help to draft a reply to a post
        Respond concisely (under 300 characters) and helpfully. If referring to a post, mention that you're responding to it."""

    async def on_message(message):
        if isinstance(message, models.Commit):
            if message.repo == bot_did:
                return

            for op in messages.ops:
                if op.action == 'create' and app.bsky.feed.post' in op.path:
                    try:
                        record = models.AppBskyFeedPost.Record(**op.value)

                        # Check for mentions
                        mentioned = False
                        if record.facets:
                            for facet in record.facets:
                                if isinstance(feature, models.AppBskyRichtextFacet.Mention):
                                    if feature.did == bot_did:
                                        mentioned = True
                                        break
                            if mentioned:
                                break

                        if mentioned:
                            print(f"New mention from {message.repo}: {record.text}")

                            # Get parent post context if available
                            context=''
                            
