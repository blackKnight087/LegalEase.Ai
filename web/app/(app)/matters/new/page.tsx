"use client";

import Link from "next/link";
import PageHeader from "@/components/ui/PageHeader";
import MatterCreateForm from "@/components/matters/MatterCreateForm";

export default function NewMatterPage() {
  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader
        title="New matter"
        subtitle="Create an isolated case workspace — documents, KB, and AI stay inside this matter"
      />
      <div className="flex-1 overflow-y-auto overflow-x-hidden le-scroll le-page-body max-w-2xl mx-auto w-full">
        <Link href="/matters" className="text-sm text-blue-700 hover:underline mb-4 inline-block">
          ← Back to matters
        </Link>
        <MatterCreateForm />
      </div>
    </div>
  );
}
