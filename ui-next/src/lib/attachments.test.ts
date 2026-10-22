import { describe, expect, it, vi } from 'vitest';
import { AttachmentUploadError, uploadAttachments } from './attachments';

/**
 * UI-10. A failed upload was only logged and the billed run started without
 * the file. Partial success was just as silent. The run must not start on a
 * partial input set.
 */
const file = (name: string) => new File(['x'], name);

describe('uploadAttachments', () => {
  it('maps every successful upload', async () => {
    const upload = vi.fn(async () => ({
      files: [{ success: true, file_id: 'f1', filename: 'a.txt', size: 1, text: 'hi' }],
    }));
    const out = await uploadAttachments([file('a.txt')], upload);
    expect(out).toEqual([
      { file_id: 'f1', filename: 'a.txt', mime_type: 'application/octet-stream', extracted_text: 'hi', size: 1 },
    ]);
  });

  it('throws naming the files when fewer succeed than were sent', async () => {
    const upload = vi.fn(async () => ({
      files: [
        { success: true, file_id: 'f1', filename: 'a.txt' },
        { success: false, filename: 'b.txt' },
      ],
    }));
    const err = await uploadAttachments([file('a.txt'), file('b.txt')], upload).catch((e) => e);
    expect(err).toBeInstanceOf(AttachmentUploadError);
    expect((err as AttachmentUploadError).failedNames).toEqual(['b.txt']);
  });

  it('throws naming every file when the request itself fails', async () => {
    const upload = vi.fn(async () => {
      throw new Error('network down');
    });
    const err = await uploadAttachments([file('a.txt'), file('b.txt')], upload).catch((e) => e);
    expect(err).toBeInstanceOf(AttachmentUploadError);
    expect((err as AttachmentUploadError).failedNames).toEqual(['a.txt', 'b.txt']);
  });
});
