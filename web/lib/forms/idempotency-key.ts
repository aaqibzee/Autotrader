/**
 * When a form sends a new `Idempotency-Key` and when it reuses one (Feature 03 slice 3.10,
 * amendment A18).
 *
 * The API stores the first answer to a key and replays it for any retry with that key and
 * the same body; the same key with a different body is a 422 (backend core/idempotency.py).
 * So a key may only be reused for an identical payload whose first attempt got **no
 * answer** (a network error or our timeout): the request may have run, and the replay
 * tells us what happened without running it twice. Every answered attempt, success or
 * 4xx, uses up its key: re-sending after a 429 or a 409 must run again, not replay.
 */
export type KeyState = {
  key: string;
  /** Whether `key` has been sent. The key minted when the form mounts is unused. */
  used: boolean;
  /** Payload of an attempt that got no answer: only this payload may reuse `key`. */
  unanswered?: string;
};

export function initialKeyState(key: string): KeyState {
  return { key, used: false };
}

export function keyForAttempt(
  state: KeyState,
  payload: string,
  mint: () => string,
): KeyState {
  if (state.unanswered === payload) return state;
  return {
    key: state.used ? mint() : state.key,
    used: true,
    unanswered: payload,
  };
}

/** The API answered (any status): the key is spent. */
export function afterAnswer(state: KeyState): KeyState {
  return { key: state.key, used: true };
}
