"use client";

import { firmChatAvatarColor, firmChatInitials } from "@/components/collaboration/firmChatUi";

export default function FirmChatAvatar({
  name,
  seed,
  size = "md",
  online,
}: {
  name: string;
  seed?: string;
  size?: "sm" | "md" | "lg";
  online?: boolean;
}) {
  const sz = size === "sm" ? "h-9 w-9 text-[10px]" : size === "lg" ? "h-12 w-12 text-sm" : "h-11 w-11 text-xs";
  const dot = size === "sm" ? "h-2.5 w-2.5 border" : "h-3 w-3 border-2";
  return (
    <span className="relative shrink-0 inline-flex">
      <span
        className={`${sz} rounded-full flex items-center justify-center font-bold text-white shadow-sm`}
        style={{ backgroundColor: firmChatAvatarColor(seed || name) }}
      >
        {firmChatInitials(name)}
      </span>
      {online !== undefined && (
        <span
          className={`absolute bottom-0 right-0 ${dot} rounded-full border-white ${
            online ? "bg-emerald-500" : "bg-slate-300"
          }`}
          aria-hidden
        />
      )}
    </span>
  );
}
