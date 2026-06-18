"use client";

import Image from "next/image";
import { FIRM_DISPLAY_NAME } from "@/lib/brand";

const FIRM_LOGO_PNG = "/legalease-logo.png";

type Props = {
  subtitle?: string;
  invoiceNumber?: string;
  invoiceDate?: string;
  dueDate?: string;
  className?: string;
};

/** Matches PDF invoice header — navy bar, logo, LegalEase.Ai */
export default function InvoiceBrandHeader({
  subtitle = "Professional Legal Services Invoice",
  invoiceNumber,
  invoiceDate,
  dueDate,
  className = "",
}: Props) {
  return (
    <div
      className={`flex justify-between items-center gap-4 px-4 py-3 rounded-t-lg ${className}`}
      style={{ backgroundColor: "#1e3a5f" }}
    >
      <div className="flex items-center gap-3 min-w-0">
        <Image
          src={FIRM_LOGO_PNG}
          alt=""
          width={44}
          height={44}
          className="shrink-0 rounded-lg bg-white p-1"
          aria-hidden
          onError={(e) => {
            const img = e.currentTarget;
            if (!img.src.endsWith(".svg")) img.src = "/legalease-logo.svg";
          }}
        />
        <div>
          <p className="text-white font-bold text-lg leading-tight tracking-tight">
            LegalEase<span className="text-[#d4af37] font-semibold">.Ai</span>
          </p>
          <p className="text-slate-300 text-[11px] mt-0.5">{subtitle}</p>
        </div>
      </div>
      {(invoiceNumber || invoiceDate || dueDate) && (
        <div className="text-right text-xs text-slate-200 shrink-0">
          {invoiceNumber && <p className="font-semibold text-white text-sm">{invoiceNumber}</p>}
          {invoiceDate && <p>Date: {invoiceDate}</p>}
          {dueDate && <p>Due: {dueDate}</p>}
        </div>
      )}
    </div>
  );
}

export { FIRM_DISPLAY_NAME };
