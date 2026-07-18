import { openDB, DBSchema } from 'idb';
import { Conversation } from './types';

interface ARADB extends DBSchema {
  conversations: {
    key: string;
    value: Conversation;
    indexes: { conversation_id: string; timestamp: string };
  };
}

const DB_NAME = 'ARA_Pipeline_v2';
const DB_VERSION = 3;
const STORE_NAME = 'conversations';
const PAGE_SIZE = 50;

export async function getDB() {
  return openDB<ARADB>(DB_NAME, DB_VERSION, {
    upgrade(db, oldVersion, _newVersion, transaction) {
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: 'id' });
        store.createIndex('conversation_id', 'conversation_id', { unique: false });
        store.createIndex('timestamp', 'timestamp', { unique: false });
      } else if (transaction) {
        const store = transaction.objectStore(STORE_NAME);
        if (oldVersion < 2 && !store.indexNames.contains('conversation_id')) {
          store.createIndex('conversation_id', 'conversation_id', { unique: false });
        }
        if (oldVersion < 3 && !store.indexNames.contains('timestamp')) {
          store.createIndex('timestamp', 'timestamp', { unique: false });
        }
      }
    },
  });
}

export async function saveConversation(data: Conversation): Promise<string> {
  const db = await getDB();
  const record: Conversation = {
    id: data.id || Date.now().toString(),
    conversation_id: data.conversation_id || data.id || Date.now().toString(),
    turn_number: data.turn_number || 1,
    timestamp: data.timestamp || new Date().toISOString(),
    problem: data.problem,
    phases: data.phases,
    errors: data.errors || [],
    preset: data.preset || 'unknown',
    method: data.method || 'multi-perspective',
    total_tokens: data.total_tokens || null,
    duration: data.duration,
    kind: data.kind || 'pipeline',
    response_content: data.response_content,
    images: data.images,
    prompt_meta: data.prompt_meta,
  };
  await db.put(STORE_NAME, record);
  return record.id;
}

export async function loadAllConversations(): Promise<Conversation[]> {
  const db = await getDB();
  const results = await db.getAll(STORE_NAME);
  return results.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
}

export async function loadConversation(id: string): Promise<Conversation | undefined> {
  const db = await getDB();
  return db.get(STORE_NAME, id);
}

export async function loadConversationsByThread(conversationId: string): Promise<Conversation[]> {
  const db = await getDB();
  const index = db.transaction(STORE_NAME).store.index('conversation_id');
  return index.getAll(conversationId);
}

export async function deleteConversation(id: string): Promise<void> {
  const db = await getDB();
  await db.delete(STORE_NAME, id);
}

export interface ConversationPage {
  items: Conversation[];
  nextCursor?: IDBValidKey;
}

export async function loadConversationsPage(
  cursor?: IDBValidKey,
  direction: IDBCursorDirection = 'prev',
): Promise<ConversationPage> {
  const db = await getDB();
  const tx = db.transaction(STORE_NAME, 'readonly');
  const store = tx.objectStore(STORE_NAME);
  const index = store.index('timestamp');
  const results: Conversation[] = [];
  let lastCursor: IDBValidKey | undefined;

  const range = cursor === undefined
    ? null
    : direction === 'prev'
      ? IDBKeyRange.upperBound(cursor, true)
      : IDBKeyRange.lowerBound(cursor, true);

  let cursorResult = await index.openCursor(range, direction);

  while (cursorResult && results.length < PAGE_SIZE) {
    results.push(cursorResult.value as Conversation);
    lastCursor = cursorResult.key;
    cursorResult = await cursorResult.continue();
  }

  return { items: results, nextCursor: lastCursor };
}

export async function clearAllConversations(): Promise<void> {
  const db = await getDB();
  await db.clear(STORE_NAME);
}
