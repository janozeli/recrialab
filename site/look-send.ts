// Sends the look on the mannequin to the team, straight from the fitting room: no image to save and pass on.
import { checkSentLook, INBOX_LIMITS, INBOX_PATH, type SentLook } from './look-inbox';

/**
 * Posts the look and resolves only when the server's whole answer has arrived and says the look was kept.
 * Stopping at the status line would confirm on the headers alone and leave the rest of the answer unread: the
 * request then ends by itself or is dropped with the page, whichever comes first (seen as an intermittent
 * "failed /api/looks" on the emulated Pixel). A connection that hangs ends in an error, not in a wait for ever.
 */
export async function postLook(look: SentLook, send: typeof fetch = fetch, timeoutMs = 20_000): Promise<void> {
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), timeoutMs);
  try {
    const response = await send(INBOX_PATH, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(look),
      signal: abort.signal,
    });
    const answer = await response.json() as { ok?: boolean };
    if (!response.ok || answer?.ok !== true) throw new Error(`HTTP ${response.status}`);
  } finally {
    clearTimeout(timer);
  }
}

/** What the author wrote last time (nickname and class), kept on the phone for the next look. */
const REMEMBER = 'recrialab-sender';

export interface LookSend {
  /** Whether a whole look is on the mannequin, with the reason shown on the button when it is not. */
  setReady(ready: boolean, title: string): void;
}

export function initLookSend(current: () => { look: string; names: string }, closed: () => void): LookSend {
  const $ = <T extends HTMLElement>(id: string): T => {
    const el = document.getElementById(id);
    if (!el) throw new Error(`missing required element: #${id}`);
    return el as T;
  };
  const button = $<HTMLButtonElement>('send-look');
  const dialog = $<HTMLDialogElement>('look-send-dialog');
  const form = $<HTMLFormElement>('send-form');
  const done = $('send-done');
  const error = $('send-error');
  const submit = $<HTMLButtonElement>('send-submit');
  const fields = {
    credit: $<HTMLInputElement>('send-credit'),
    group: $<HTMLInputElement>('send-group'),
    name: $<HTMLInputElement>('send-name'),
    note: $<HTMLTextAreaElement>('send-note'),
  };
  for (const [field, input] of Object.entries(fields)) input.maxLength = INBOX_LIMITS[field as keyof typeof fields];
  let look = '';
  let sending = false;

  button.addEventListener('click', () => {
    const now = current();
    if (!now.look) return;
    look = now.look;
    $('send-names').textContent = now.names;
    $('send-code').textContent = `LOOK ${look.replace('.', ' + ')}`;
    try {
      const saved = JSON.parse(localStorage.getItem(REMEMBER) ?? 'null');
      if (!fields.credit.value) fields.credit.value = String(saved?.credit ?? '');
      if (!fields.group.value) fields.group.value = String(saved?.group ?? '');
    } catch { /* private window: nothing remembered */ }
    form.hidden = false;
    done.hidden = true;
    error.hidden = true;
    dialog.showModal();
  });
  $('send-close').addEventListener('click', () => dialog.close());
  $('send-finish').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', closed);

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (sending) return;
    const checked = checkSentLook({ look, credit: fields.credit.value, group: fields.group.value, name: fields.name.value, note: fields.note.value });
    if (!checked.ok) {
      error.hidden = false;
      return;
    }
    sending = true;
    submit.disabled = true;
    submit.setAttribute('aria-busy', 'true');
    error.hidden = true;
    try {
      await postLook(checked.look);
      try {
        localStorage.setItem(REMEMBER, JSON.stringify({ credit: checked.look.credit, group: checked.look.group }));
      } catch { /* private window */ }
      // The next look starts with a clean name and note; nickname and class stay.
      fields.name.value = '';
      fields.note.value = '';
      form.hidden = true;
      done.hidden = false;
      $('send-finish').focus();
    } catch {
      error.hidden = false;
    } finally {
      sending = false;
      submit.disabled = false;
      submit.setAttribute('aria-busy', 'false');
    }
  });

  return {
    setReady(ready, title) {
      button.disabled = !ready;
      button.title = title;
    },
  };
}
