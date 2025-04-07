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
                            if record.reply:
                                try:
                                    parent_post = await bluesky_client.get_post(record.reply.parent.uri)
                                    context = f"Post being discussed:\n{parent_post.text}"
                                except Exception as e:
                                    print(f"Couldn't fetch parent post: {e}")


                            # Clean query text
                            query = record.text.replace(f"@{bot_handle}", "").strip()

                            # Response
                            response = openai_client.chat.completions.create(
                                model='gpt-4o-mini',
                                messages=[
                                    {'role': 'system', 'content': SYSTEM_PROMPT},
                                    {'role': 'user', 'content': f"{context}\n\nUser's rewuest: {query}"}
                                ],
                                max_tokens=200
                            ).choices[0].message.content.strip()

                            response = response[:280]

                            rkey = op.path.split('/')[-1]
                            parent_uri = f"at://{message.repo}/app.bsky.feed.post/{rkey}"
                            parent_cid = op.cid

                            if record.reply:
                                root_uri = record.reply.root.uri
                                root_cid = record.reply.root.cid
                            else:
                                root_uri = parent_uri
                                root_cid = parent_cid

                            reply_ref = models.AppBskyFeedPost.ReplyRef(
                                parent=models.AppBskyFeedPost.ReplyRefParent(
                                    uri=parent_uri,
                                    cid=parent_cid
                                ),
                                root=models.AppBsjyFeedPost.RepltTefRoot(
                                    uri=root_uri,
                                    cid=root_cid
                                )
                            )

                            await bluesky_client.send_post(
                                text=response,
                                reply=reply_ref
                            )
                            print(f"Posted response: {response}")

                    except Exception as e:
                        print(f"Error processing post: {e}")

    await bluesky_client.subscribe_repos(on_message)

if __name__ = '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())

    except KeyboardInterrupt:
        print('Bot stopped.')
