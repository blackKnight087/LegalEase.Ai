export type StageEmptyContent = {
  icon: string;
  headline: string;
  description: string;
  nextAction: string;
  ctaLabel: string;
  ctaHref?: string;
};

export const STAGE_EMPTY_CONTENT: Record<string, StageEmptyContent> = {
  NEW_INQUIRY: {
    icon: "📥",
    headline: "No inquiries yet",
    description: "New client submissions from your intake portal or manual entry appear here first.",
    nextAction: "Share your public intake link or add a lead manually.",
    ctaLabel: "Add lead",
    ctaHref: "/intake/new",
  },
  AI_REVIEW: {
    icon: "🤖",
    headline: "AI review queue empty",
    description: "Leads move here after intake AI classifies case type, urgency, and document needs.",
    nextAction: "Run analysis on new inquiries to populate this stage.",
    ctaLabel: "View inquiries",
  },
  CONSULTATION_SCHEDULED: {
    icon: "📅",
    headline: "No consultations booked",
    description: "High-intent leads with scheduled calls show here for prep and follow-up.",
    nextAction: "Schedule consultations from AI-reviewed leads.",
    ctaLabel: "Open pipeline",
  },
  DOCUMENTS_REQUESTED: {
    icon: "📄",
    headline: "No document requests",
    description: "When clients must upload FIR, ID, or evidence, move qualified leads here.",
    nextAction: "Request documents after initial consultation.",
    ctaLabel: "Request documents",
  },
  DOCUMENTS_RECEIVED: {
    icon: "✅",
    headline: "Awaiting uploads",
    description: "Leads appear here once clients upload requested documents for verification.",
    nextAction: "Move leads from Documents Requested when uploads arrive.",
    ctaLabel: "Check portal",
  },
  QUALIFIED: {
    icon: "⭐",
    headline: "No qualified leads",
    description: "Leads ready for engagement terms and retainer discussion land in this stage.",
    nextAction: "Qualify after documents and consultation are complete.",
    ctaLabel: "Review leads",
  },
  ENGAGEMENT_LETTER_SENT: {
    icon: "📝",
    headline: "No letters pending",
    description: "Track leads awaiting signature on engagement terms and scope of work.",
    nextAction: "Send engagement letter from qualified leads.",
    ctaLabel: "Send letter",
  },
  RETAINER_PAID: {
    icon: "💰",
    headline: "No retainers recorded",
    description: "Confirmed fee payments before matter conversion are tracked here.",
    nextAction: "Record retainer once engagement is signed.",
    ctaLabel: "Record payment",
  },
  MATTER_CREATED: {
    icon: "⚖️",
    headline: "No matters yet",
    description: "Converted leads open as matters in your practice module.",
    nextAction: "Convert retainer-paid leads to active matters.",
    ctaLabel: "Go to matters",
    ctaHref: "/matters",
  },
  CLOSED_WON: {
    icon: "🏆",
    headline: "No closed wins",
    description: "Successfully completed engagements are archived here for reporting.",
    nextAction: "Close won when matter work concludes.",
    ctaLabel: "View reports",
  },
  CLOSED_LOST: {
    icon: "📋",
    headline: "No lost leads",
    description: "Declined or unresponsive opportunities help refine intake quality.",
    nextAction: "Move declined leads here to keep pipeline accurate.",
    ctaLabel: "Learn why",
  },
};

export function getStageEmptyContent(stage: string, hint?: string): StageEmptyContent {
  const base = STAGE_EMPTY_CONTENT[stage];
  if (!base) {
    return {
      icon: "📌",
      headline: "No leads in this stage",
      description: hint || "Drag a lead here when ready to advance the pipeline.",
      nextAction: "Keep stages updated for accurate revenue forecasting.",
      ctaLabel: "Add lead",
      ctaHref: "/intake/new",
    };
  }
  if (hint) return { ...base, description: hint };
  return base;
}
