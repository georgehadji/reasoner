import { uploadFiles } from './api-client';

export interface UploadedAttachment {
  file_id: string;
  filename: string;
  mime_type: string;
  extracted_text: string;
  size: number;
}

/** Thrown when any attachment did not make it; a billed run must not start without it. */
export class AttachmentUploadError extends Error {
  constructor(readonly failedNames: string[]) {
    super(`Could not upload: ${failedNames.join(', ')}`);
    this.name = 'AttachmentUploadError';
  }
}

type Upload = (files: File[]) => Promise<{ files?: Array<{
  success?: boolean;
  file_id?: string;
  filename?: string;
  mime_type?: string;
  text?: string;
  size?: number;
}> }>;

/** All-or-nothing: returns one entry per file, or throws naming the ones that failed. */
export async function uploadAttachments(
  files: File[],
  upload: Upload = uploadFiles,
): Promise<UploadedAttachment[]> {
  let results;
  try {
    results = (await upload(files)).files ?? [];
  } catch {
    throw new AttachmentUploadError(files.map((f) => f.name));
  }
  const ok = results.filter((r) => r.success && r.file_id);
  if (ok.length < files.length) {
    const done = new Set(ok.map((r) => r.filename));
    const failed = files.map((f) => f.name).filter((n) => !done.has(n));
    throw new AttachmentUploadError(failed.length ? failed : files.map((f) => f.name));
  }
  return ok.map((r) => ({
    file_id: r.file_id!,
    filename: r.filename!,
    mime_type: r.mime_type || 'application/octet-stream',
    extracted_text: r.text || '',
    size: r.size || 0,
  }));
}
