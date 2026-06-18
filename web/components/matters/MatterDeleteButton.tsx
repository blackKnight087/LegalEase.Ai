"use client";

import { useState } from "react";
import MatterDeleteModal from "@/components/matters/MatterDeleteModal";

export default function MatterDeleteButton({
  matterId,
  matterName,
  onDeleted,
  className = "",
  label = "Delete matter",
}: {
  matterId: string;
  matterName: string;
  onDeleted?: () => void;
  className?: string;
  label?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={
          className ||
          "px-3 py-1.5 text-sm font-medium text-red-700 border border-red-300 rounded-lg hover:bg-red-50"
        }
      >
        {label}
      </button>
      <MatterDeleteModal
        matterId={matterId}
        matterName={matterName}
        open={open}
        onClose={() => setOpen(false)}
        onDeleted={() => {
          setOpen(false);
          onDeleted?.();
        }}
      />
    </>
  );
}
