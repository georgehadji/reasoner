'use client';

import { Tooltip } from '@/components/ui/Tooltip';
import { useProvenanceCapabilities } from '@/hooks/useProvenanceCapabilities';
import { cn } from '@/lib/utils';

export interface EgressSettingsValue {
  layerA: boolean;
  imageMetadata: boolean;
}

interface EgressSettingsProps {
  value: EgressSettingsValue;
  onChange: (value: EgressSettingsValue) => void;
  className?: string;
}

interface ToggleRowProps {
  id: string;
  label: string;
  description: string;
  checked: boolean;
  onChange?: (checked: boolean) => void;
  disabled?: boolean;
  lockedReason?: string;
}

function ToggleRow({ id, label, description, checked, onChange, disabled, lockedReason }: ToggleRowProps) {
  const row = (
    <label
      htmlFor={id}
      className={cn(
        'flex items-start justify-between gap-3 rounded-[var(--radius)] border border-[var(--border)] p-3',
        disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'
      )}
    >
      <span>
        <span className="block text-sm font-medium text-[var(--text)]">{label}</span>
        <span className="block text-[length:var(--text-xs)] text-[var(--text-2)]">{description}</span>
      </span>
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange?.(e.target.checked)}
        className="mt-1 h-4 w-4 shrink-0 cursor-pointer rounded border-[var(--border)] disabled:cursor-not-allowed"
      />
    </label>
  );
  return disabled && lockedReason ? <Tooltip text={lockedReason}>{row}</Tooltip> : row;
}

/** Per-run provenance-scrubbing toggles. Controlled component: the caller owns
 * `value`/`onChange` -- this renders the choices, it doesn't decide policy.
 *
 * Copy discipline (docs/plans/watermark-removal-integration.md Part V.7):
 * never "undetectable", never "proves human-written", never "bypasses AI
 * detection" -- only what was verifiably removed, or what's best-effort.
 */
export function EgressSettings({ value, onChange, className }: EgressSettingsProps) {
  const { capabilities } = useProvenanceCapabilities();

  return (
    <div className={cn('grid gap-2', className)}>
      <ToggleRow
        id="egress-layer-a"
        label="Remove invisible characters"
        description="Strips zero-width and other edit-based Unicode carriers from the response text."
        checked={value.layerA}
        onChange={(layerA) => onChange({ ...value, layerA })}
      />
      <ToggleRow
        id="egress-image-metadata"
        label="Strip image metadata"
        description="Removes C2PA/EXIF/XMP provenance metadata from uploaded images."
        checked={value.imageMetadata}
        onChange={(imageMetadata) => onChange({ ...value, imageMetadata })}
      />
      <ToggleRow
        id="egress-layer-b"
        label="Statistical rewrite"
        description="Best-effort rewrite to reduce statistical token-sampling patterns. Cannot certify removal; adds cost and may affect quality."
        checked={false}
        disabled
        lockedReason={
          capabilities.layer_b_enabled
            ? 'Not yet available for this run.'
            : 'Not available on this deployment yet.'
        }
      />
    </div>
  );
}
