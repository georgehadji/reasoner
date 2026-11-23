/**
 * Every store that holds a user's data, in erase order, mirrored from the
 * backend registry `src/reasoner/api/user_data.py` (`user_data_stores()`,
 * pinned by `tests/architecture/test_user_data_registry.py`).
 *
 * `name` is the store name the export and erasure receipts use.
 * `encrypted` is set only where the code encrypts before writing:
 * events (postgres_store.py), uploads (uploader.py), vectors
 * (vector_store.py). Unset means "not claimed", not "plaintext".
 * `account` marks the two stores `DELETE /api/user/data` leaves in place
 * (ACCOUNT_STORE_NAMES); only `POST /api/account/delete` removes them.
 */
export interface UserDataStore {
  name: string;
  label: string;
  encrypted?: boolean;
  account?: boolean;
}

export const USER_DATA_STORES: UserDataStore[] = [
  { name: 'events', label: 'Runs, phase by phase', encrypted: true },
  { name: 'vectors', label: 'Index of your uploads', encrypted: true },
  { name: 'uploads', label: 'Uploaded files', encrypted: true },
  { name: 'history', label: 'Conversation history' },
  { name: 'neuro', label: 'Long-term memory' },
  { name: 'run_cache', label: 'Cached run results' },
  { name: 'token_cache', label: 'Token cache' },
  { name: 'valkey', label: 'Cache keys' },
  { name: 'unsettled_runs', label: 'Runs not yet billed' },
  { name: 'error_log', label: 'Error reports' },
  { name: 'query_log', label: 'Usage log' },
  { name: 'credit_ledger', label: 'Credit ledger' },
  { name: 'quota', label: 'Quota' },
  { name: 'subscriptions', label: 'Subscription' },
  { name: 'profile', label: 'Profile', account: true },
  { name: 'identity', label: 'Sign-in identity', account: true },
];

/** Store names `DELETE /api/user/data` erases: everything but the account. */
export const ERASED_BY_DATA_DELETE = USER_DATA_STORES.filter((s) => !s.account).map((s) => s.name);
