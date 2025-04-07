/* firehose-bot.ts */

import 'dotenv/config';

import { Firehose } from '@atproto/sync';
import { IdResolver } from '@atproto/identity';
import { AtpAgent, AppBskyFeedPost, ComAtprotoRepoStrongRef } from '@atproto/api';
import { OpenAI } from 'openai';

// -- ENV
const BLUESKY_HANDLE = process.env.BLUESKY_HANDLE || '';
const BLUESKY_APP_PASSWORD = process.env.BLUESKY_APP_PASSWORD || '';
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || '';

// -- Initialize an AtpAgent for logging in & posting replies
const agent = new AtpAgent({ service: 'https://bsky.social' });

// -- Initialize OpenAI
const openai = new OpenAI({ apiKey: OPENAI_API_KEY });

// -- We'll also need an IdResolver for Firehose (for handle & DID lookups)
const idResolver = new IdResolver();

// System prompt for the AI
const SYSTEM_PROMPT = `You are a helpful assistant on Bluesky. Respond concisely (<=300 chars).
If referring to a post, mention that you're responding to it.`;

// Basic chat message shape for OpenAI
interface ChatCompletionRequestMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

/**
 * Generate short replies using OpenAI
 */
async function generateReply(context: string, userText: string): Promise<string> {
  try {
    const messages: ChatCompletionRequestMessage[] = [
      { role: 'system', content: SYSTEM_PROMPT },
      { role: 'user', content: `${context}\n\nUser's request: ${userText}` },
    ];

    const resp = await openai.chat.completions.create({
      model: 'gpt-3.5-turbo', // or gpt-4 if you have access
      messages,
      max_tokens: 200,
    });
    const raw = resp.choices[0]?.message?.content?.trim() || '';
    return raw.slice(0, 280); // Keep reply short for Bluesky
  } catch (err) {
    console.error('[OpenAI Error]', err);
    return 'Sorry, I encountered an error generating a response.';
  }
}

/**
 * Check if the bot is mentioned, then post an AI-generated reply if so
 */
async function handlePost(
  record: AppBskyFeedPost.Record,
  repoDid: string,
  botDid: string,
  botHandle: string
) {
  const text = record.text || '';
  if (!text) return;

  // Check mention
  let mentioned = false;
  if (record.facets) {
    for (const facet of record.facets) {
      for (const feature of facet.features) {
        if (feature.$type === 'app.bsky.richtext.facet#mention') {
          // (feature as any).did is the DID that was mentioned
          if ((feature as any).did === botDid) {
            mentioned = true;
            break;
          }
        }
      }
      if (mentioned) break;
    }
  }
  if (!mentioned) return; // Our bot not mentioned => do nothing

  console.log(`New mention from repo=${repoDid}, text="${text}"`);

  // Optionally fetch parent context if there's a reply
  let context = '';
  if (record.reply?.parent?.uri) {
    try {
      const parentResult = await agent.app.bsky.feed.getPostThread({
        uri: record.reply.parent.uri,
      });
      const thread = parentResult.data.thread;
      if (thread && 'post' in thread && (thread as any).post?.record?.text) {
        context = `Post being discussed:\n${(thread as any).post.record.text}`;
      }
    } catch (err) {
      console.warn('Could not fetch parent post:', err);
    }
  }

  // Clean user text if desired
  const cleanedText = text.replace(`@${botHandle}`, '').trim();

  // Generate an AI-based reply
  const replyText = await generateReply(context, cleanedText);

  // Build references so we reply in the same thread
  const parentRef: ComAtprotoRepoStrongRef.Main = {
    uri: record.uri as string,
    cid: record.cid as string,
  };
  let rootRef: ComAtprotoRepoStrongRef.Main = parentRef;
  if (record.reply?.root?.uri && record.reply?.root?.cid) {
    rootRef = {
      uri: record.reply.root.uri as string,
      cid: record.reply.root.cid as string,
    };
  }

  // Post it as the bot
  try {
    await agent.app.bsky.feed.post.create(
      { repo: botDid },
      {
        $type: 'app.bsky.feed.post',
        text: replyText,
        createdAt: new Date().toISOString(),
        reply: {
          parent: parentRef,
          root: rootRef,
        },
      },
    );
    console.log('Posted reply:', replyText);
  } catch (err) {
    console.error('Error posting reply:', err);
  }
}

async function main() {
  // 1) Log in with your bot
  await agent.login({
    identifier: BLUESKY_HANDLE,
    password: BLUESKY_APP_PASSWORD,
  });
  console.log(`Logged in as ${BLUESKY_HANDLE}`);

  // 2) Get bot DID & handle
  const prof = await agent.app.bsky.actor.getProfile({ actor: BLUESKY_HANDLE });
  const botDid = prof.data.did;
  const botHandle = prof.data.handle;
  console.log(`Bot DID=${botDid}, Bot handle=${botHandle}`);

  // 3) Create a Firehose for real-time events
  const firehose = new Firehose({
    idResolver,
    service: 'wss://bsky.network', // Or wss://bsky.social, depending on your config
    handleEvt: async (evt: { event: string; collection?: string; record?: any; did?: string; [key: string]: any }) => {
      // The Firehose can emit identity, account, create, update, delete events
      switch (evt.event) {
        case 'create': {
          const createEvt = evt as { event: string; collection?: string; record?: any; did?: string; [key: string]: any };
          // Check if it's a feed post
          if (createEvt.collection === 'app.bsky.feed.post') {
            if (AppBskyFeedPost.isRecord(createEvt.record)) {
              const record = createEvt.record as AppBskyFeedPost.Record;
              await handlePost(record, createEvt.did || '', botDid, botHandle);
            }
          }
          break;
        }
        case 'identity':
          // e.g. handle or DID updates
          break;
        case 'account':
          // e.g. new accounts, password changes
          break;
        case 'update':
          // record updates
          break;
        case 'delete':
          // record deletions
          break;
        default:
          break;
      }
    },
    onError: (err: Error) => {
      console.error('[Firehose Error]', err);
    },
    // You can optionally filter events or disable signature checks:
    // filterCollections: ['app.bsky.feed.post'],
    // unauthenticatedCommits: true,
    // ...
  });

  // 4) Start the Firehose
  firehose.start();
  console.log('Firehose started. Listening for events...');
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});