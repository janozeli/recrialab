// Sends the look on the mannequin to the team, straight from the fitting room: no image to save and pass on.
import { checkSentLook, INBOX_LIMITS, INBOX_PATH } from './look-inbox';

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
    // A connection that hangs ends in the error notice, not in a button busy for ever.
    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), 20_000);
    try {
      const response = await fetch(INBOX_PATH, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(checked.look),
        signal: abort.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
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
      clearTimeout(timer);
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
