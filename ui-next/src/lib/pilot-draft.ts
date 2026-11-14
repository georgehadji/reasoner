/** sessionStorage key the landing page's pilot dialog writes and /contact
 *  reads once. Session-scoped on purpose: a problem description must not
 *  travel in a URL, where it would reach server logs and history. */
export const PILOT_DRAFT_KEY = 'reasoner:pilot-draft';
