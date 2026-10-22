"use client";

import type { ApiFormConflict } from "@/lib/forms/use-api-form";
import { PROBLEM_UI } from "@/lib/api/problem-ui";
import { Button } from "./button";
import { Modal } from "./overlay";

/**
 * 409 `stale_update` (Feature 03 §3): someone else saved while you were editing. Shows
 * what differs between your version and theirs, then lets you take theirs or re-apply
 * yours on top of it. Not dismissable by a stray tap: either choice is deliberate.
 * Driven by `useApiForm`'s `conflict`, `reloadTheirs` and `reapplyMine`.
 */
export function ConflictDialog({
  conflict,
  onReloadTheirs,
  onReapplyMine,
  onDismiss,
}: {
  conflict: ApiFormConflict | undefined;
  onReloadTheirs: () => void;
  onReapplyMine: () => void;
  onDismiss: () => void;
}) {
  const ui = PROBLEM_UI.stale_update;
  return (
    <Modal
      footer={() => (
        <div className="flex flex-wrap justify-end gap-2">
          <Button onClick={onReloadTheirs} variant="secondary">
            Reload theirs
          </Button>
          <Button onClick={onReapplyMine}>Re-apply mine</Button>
        </div>
      )}
      isDismissable={false}
      isOpen={conflict !== undefined}
      onOpenChange={(open) => {
        if (!open) onDismiss();
      }}
      title={ui.title}
    >
      <p className="text-ink-soft">{ui.message}</p>
      {conflict && conflict.changes.length > 0 ? (
        <table className="mt-4 w-full text-left text-sm">
          <caption className="sr-only">
            Differences between your version and theirs
          </caption>
          <thead>
            <tr className="border-b border-line text-ink-muted">
              <th className="py-2 pr-3 font-semibold" scope="col">
                Field
              </th>
              <th className="py-2 pr-3 font-semibold" scope="col">
                Yours
              </th>
              <th className="py-2 font-semibold" scope="col">
                Theirs
              </th>
            </tr>
          </thead>
          <tbody>
            {conflict.changes.map((change) => (
              <tr className="border-b border-line align-top" key={change.field}>
                <th className="py-2 pr-3 font-semibold text-ink" scope="row">
                  {change.label}
                </th>
                <td className="py-2 pr-3 break-words">{change.mine}</td>
                <td className="py-2 break-words">{change.theirs}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="mt-4 text-sm text-ink-muted">
          The fields you can edit here are the same in both versions.
        </p>
      )}
    </Modal>
  );
}
