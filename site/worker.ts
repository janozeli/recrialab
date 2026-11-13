/**
 * The server side of the site. Only `/api/*` reaches this Worker (wrangler.jsonc, `run_worker_first`); every page and
 * file is served straight from the static assets, so the fitting room does not depend on this code to open.
 * The runtime accepts only handlers and Durable Object classes as exports of this file: the rest lives in inbox-server.ts.
 */
import { handle, LookInbox } from './inbox-server';

export { LookInbox };
export default { fetch: handle };
