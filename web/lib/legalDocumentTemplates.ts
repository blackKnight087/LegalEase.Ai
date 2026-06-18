/** Firm-ready legal document bodies — substantive clauses, not bracket placeholders. */
import { EXECUTION_BLOCK_HTML } from "@/lib/legalDocumentFormat";

export type LegalTemplateId =
  | "agreement"
  | "nda"
  | "petition"
  | "affidavit"
  | "legal_notice"
  | "employment_contract"
  | "written_statement"
  | "reply"
  | "bail_application"
  | "custom";

export type LegalTemplateMeta = {
  id: LegalTemplateId;
  label: string;
  category: string;
  description: string;
};

export const LEGAL_TEMPLATES: LegalTemplateMeta[] = [
  { id: "agreement", label: "Agreement", category: "Commercial", description: "Full commercial terms, indemnity, arbitration, execution" },
  { id: "nda", label: "NDA", category: "Commercial", description: "Confidentiality, term, remedies, governing law" },
  { id: "petition", label: "Petition", category: "Litigation", description: "Court heading, numbered facts, prayer, verification" },
  { id: "affidavit", label: "Affidavit", category: "Litigation", description: "Deponent statement, verification, place and date" },
  { id: "legal_notice", label: "Legal Notice", category: "Litigation", description: "Demand notice with statutory timeline" },
  { id: "employment_contract", label: "Employment", category: "Employment", description: "Appointment, compensation, IP, termination" },
  { id: "written_statement", label: "Written Statement", category: "Litigation", description: "Para-wise reply under Order VIII CPC" },
  { id: "reply", label: "Reply", category: "Litigation", description: "Formal reply to notice or application" },
  { id: "bail_application", label: "Bail Application", category: "Criminal", description: "Section 439 CrPC style grounds and prayer" },
  { id: "custom", label: "Blank structured", category: "General", description: "Minimal sections with execution block" },
];

const SKELETONS: Record<LegalTemplateId, string> = {
  agreement: `
<h1 style="text-align:center">AGREEMENT</h1>
<p style="text-align:center"><strong>{{MatterName}}</strong></p>
<p>This Agreement ("Agreement") is made at {{Venue}} on this ________ day of ________ 2026.</p>
<h2>1. Parties</h2>
<p><strong>Party A:</strong> {{ClientName}}, having its registered office / residence at {{Address}} (hereinafter "Party A").</p>
<p><strong>Party B:</strong> {{OpposingParty}}, having address at ________ (hereinafter "Party B"). Party A and Party B are collectively the "Parties".</p>
<h2>2. Recitals</h2>
<p>WHEREAS Party A and Party B wish to record their mutual understandings in connection with {{MatterName}};</p>
<p>WHEREAS the Parties have agreed to enter into this Agreement on the terms set out below.</p>
<p>NOW, THEREFORE, in consideration of the mutual covenants herein, the Parties agree as follows:</p>
<h2>3. Definitions</h2>
<p><strong>"Effective Date"</strong> means the date of last signature below.</p>
<p><strong>"Confidential Information"</strong> means all non-public information disclosed by either Party in connection with this Agreement.</p>
<p><strong>"Services"</strong> means the work, deliverables, or obligations described in Schedule A (if any) or as otherwise agreed in writing.</p>
<h2>4. Scope and obligations</h2>
<p>Party B shall perform the Services with reasonable skill and care, in accordance with applicable law and any specifications agreed between the Parties. Party A shall provide timely instructions, access, and cooperation reasonably required for performance.</p>
<h2>5. Consideration and payment</h2>
<p>In consideration of the Services, Party A shall pay Party B the fees and expenses set out in Schedule A or as invoiced monthly within fifteen (15) days of receipt of a valid tax invoice. Late amounts may attract interest at 1.5% per month or the maximum permitted by law, whichever is lower.</p>
<h2>6. Confidentiality</h2>
<p>Each Party shall keep Confidential Information strictly confidential, use it only for the purpose of this Agreement, and protect it with at least the same degree of care as it uses for its own confidential information. This obligation survives for three (3) years after termination, except for trade secrets which survive so long as they remain confidential.</p>
<h2>7. Term and termination</h2>
<p>This Agreement commences on the Effective Date and continues until completed or terminated. Either Party may terminate for convenience on thirty (30) days' written notice, or immediately for material breach not cured within fifteen (15) days of notice. Accrued rights and surviving clauses (including confidentiality, indemnity, and dispute resolution) continue after termination.</p>
<h2>8. Indemnity</h2>
<p>Each Party shall indemnify and hold harmless the other from losses, claims, and expenses (including reasonable legal fees) arising from its breach of this Agreement, negligence, or violation of law, except to the extent caused by the indemnified Party's own misconduct.</p>
<h2>9. Limitation of liability</h2>
<p>Except for fraud, wilful misconduct, or indemnity obligations, neither Party's aggregate liability shall exceed the fees paid or payable under this Agreement in the twelve (12) months preceding the claim. Neither Party is liable for indirect or consequential damages.</p>
<h2>10. Force majeure</h2>
<p>Neither Party is liable for delay or failure due to events beyond reasonable control (including acts of God, war, epidemic, government order, or utility failure), provided it notifies the other promptly and uses reasonable efforts to resume performance.</p>
<h2>11. Dispute resolution</h2>
<p>The Parties shall attempt good-faith negotiation for fifteen (15) days. Failing settlement, disputes shall be referred to arbitration under the Arbitration and Conciliation Act, 1996, by a sole arbitrator appointed mutually, seated at {{Venue}}, in English. Courts at {{Venue}} shall have exclusive jurisdiction for interim relief and enforcement.</p>
<h2>12. Governing law</h2>
<p>This Agreement is governed by the laws of India.</p>
<h2>13. Miscellaneous</h2>
<p>This Agreement is the entire understanding between the Parties. Amendments must be in writing signed by both Parties. Notices shall be sent to registered addresses by registered post or email with confirmation.</p>
${EXECUTION_BLOCK_HTML}
`,
  nda: `
<h1 style="text-align:center">NON-DISCLOSURE AGREEMENT</h1>
<p>This Non-Disclosure Agreement is entered into at {{Venue}} on ________ 2026 between {{ClientName}} ("Disclosing Party") and {{OpposingParty}} ("Receiving Party") in relation to {{MatterName}} ("Purpose").</p>
<h2>1. Confidential Information</h2>
<p>Confidential Information means all non-public technical, commercial, financial, or legal information disclosed in any form, including analyses, copies, and derivatives, except information that is public without breach, independently developed, or lawfully obtained from a third party without restriction.</p>
<h2>2. Obligations</h2>
<p>The Receiving Party shall use Confidential Information solely for the Purpose, restrict access to personnel with a need to know who are bound by similar obligations, and protect it using reasonable security measures.</p>
<h2>3. Compelled disclosure</h2>
<p>If compelled by law or court order, the Receiving Party may disclose only what is required after giving prompt notice (where lawful) to enable protective steps.</p>
<h2>4. Term</h2>
<p>Confidentiality obligations continue for three (3) years from each disclosure. Trade secrets remain protected for so long as they qualify as trade secrets.</p>
<h2>5. Remedies</h2>
<p>The Parties acknowledge that breach may cause irreparable harm and that the Disclosing Party is entitled to injunctive relief in addition to other remedies.</p>
<h2>6. Governing law and jurisdiction</h2>
<p>This Agreement is governed by the laws of India. Courts at {{Venue}} shall have exclusive jurisdiction.</p>
${EXECUTION_BLOCK_HTML}
`,
  petition: `
<h1 style="text-align:center">IN THE COURT OF {{CourtName}}</h1>
<p style="text-align:center"><strong>{{CaseNumber}}</strong></p>
<p style="text-align:center">In the matter of {{MatterName}}</p>
<h2>Between</h2>
<p><strong>{{ClientName}}</strong> … Petitioner</p>
<p><strong>And</strong></p>
<p><strong>{{OpposingParty}}</strong> … Respondent</p>
<h2>Petition under [specify statute / provision]</h2>
<p>The humble petition of the Petitioner above-named most respectfully sheweth:</p>
<h2>1. Facts</h2>
<ol class="legal-numbered">
<li>That the Petitioner is ________ and is aggrieved by the action of the Respondent.</li>
<li>That the cause of action arose at {{Venue}} and continues to subsist.</li>
<li>That the Petitioner has not approached any other forum for similar relief.</li>
</ol>
<h2>2. Grounds</h2>
<ol class="legal-numbered">
<li>That the impugned action is contrary to law and natural justice.</li>
<li>That the Petitioner is entitled to relief as prayed herein.</li>
</ol>
<h2>3. Prayer</h2>
<p>It is therefore most respectfully prayed that this Hon'ble Court may be pleased to:</p>
<ol class="legal-numbered">
<li>Issue notice to the Respondent;</li>
<li>Pass such interim and final orders as the facts warrant;</li>
<li>Award costs in favour of the Petitioner.</li>
</ol>
<h2>Verification</h2>
<p>I, ________, the Petitioner above-named, do hereby verify that the contents of paras 1 to 3 are true to my personal knowledge and belief, and that no material fact has been suppressed.</p>
<p><strong>Place:</strong> {{Venue}} &nbsp; <strong>Date:</strong> ________</p>
<p><strong>Signature of Petitioner</strong></p>
<h2>Annexures</h2>
<p>Annexure A — Copy of impugned order / communication</p>
`,
  affidavit: `
<h1 style="text-align:center">AFFIDAVIT</h1>
<p>I, <strong>{{ClientName}}</strong>, aged ________ years, residing at {{Address}}, do hereby solemnly affirm and state on oath as under:</p>
<ol class="legal-numbered">
<li>That I am the deponent herein and competent to swear this affidavit.</li>
<li>That the statements made herein are true to my personal knowledge except where stated to be on information and belief, and where so stated I believe them to be true.</li>
<li>That Annexure A annexed hereto is a true copy of ________.</li>
</ol>
<h2>Verification</h2>
<p>I, the above-named deponent, do hereby verify that the contents of the above affidavit are true to my knowledge and no material fact has been concealed therefrom.</p>
<p>Verified at {{Venue}} on this ________ day of ________ 2026.</p>
<p><strong>Deponent</strong></p>
`,
  legal_notice: `
<h1 style="text-align:center">LEGAL NOTICE</h1>
<p><strong>To,</strong><br>{{OpposingParty}}</p>
<p><strong>Under instructions from and on behalf of:</strong> {{ClientName}}</p>
<p><strong>Re:</strong> {{MatterName}} — {{CaseNumber}}</p>
<p>Sir/Madam,</p>
<p>Under instructions from my client, I hereby serve upon you the following notice:</p>
<ol class="legal-numbered">
<li>That my client and you entered into / are concerned with ________ at {{Venue}}.</li>
<li>That you have failed to ________ despite repeated requests, causing loss and prejudice to my client.</li>
<li>That your conduct constitutes breach of obligation / applicable law and my client is entitled to damages and other reliefs.</li>
</ol>
<p>You are hereby called upon to remedy the breach and pay damages of Rs. ________ within fifteen (15) days of receipt of this notice, failing which my client shall initiate appropriate civil and/or criminal proceedings at your risk as to costs and consequences.</p>
<p>This notice is issued without prejudice to all rights and remedies available in law and equity.</p>
<p><strong>Place:</strong> {{Venue}} &nbsp; <strong>Date:</strong> ________</p>
<p><strong>Advocate for {{ClientName}}</strong></p>
`,
  employment_contract: `
<h1 style="text-align:center">EMPLOYMENT AGREEMENT</h1>
<p>This Employment Agreement is made at {{Venue}} on ________ 2026 between {{ClientName}} ("Employer") and ________ ("Employee").</p>
<h2>1. Appointment</h2>
<p>The Employer appoints the Employee as ________ with effect from ________ on the terms below.</p>
<h2>2. Duties</h2>
<p>The Employee shall devote full working time and attention to the business, follow lawful policies, and report to ________.</p>
<h2>3. Compensation</h2>
<p>The Employee shall receive a gross monthly salary of Rs. ________ payable on the last working day of each month, subject to statutory deductions. Annual bonus, if any, is discretionary.</p>
<h2>4. Confidentiality and intellectual property</h2>
<p>All work product, inventions, and confidential information developed during employment belong to the Employer. The Employee shall not disclose or use such information after employment except as required by law.</p>
<h2>5. Leave and benefits</h2>
<p>The Employee is entitled to leave and benefits as per Employer policy and applicable labour laws.</p>
<h2>6. Termination</h2>
<p>Either party may terminate on thirty (30) days' written notice or payment in lieu. The Employer may terminate immediately for gross misconduct, breach, or incapacity.</p>
<h2>7. Non-solicitation</h2>
<p>For twelve (12) months after termination, the Employee shall not solicit the Employer's clients or employees with whom the Employee had material contact.</p>
<h2>8. Governing law</h2>
<p>This Agreement is governed by the laws of India. Courts at {{Venue}} shall have jurisdiction.</p>
${EXECUTION_BLOCK_HTML}
`,
  written_statement: `
<h1 style="text-align:center">WRITTEN STATEMENT</h1>
<p><strong>Court:</strong> {{CourtName}} &nbsp; <strong>Suit / Case No.:</strong> {{CaseNumber}}</p>
<p><strong>Defendant:</strong> {{ClientName}}</p>
<p>The above-named Defendant most respectfully submits this written statement in reply to the plaint:</p>
<h2>Preliminary objections</h2>
<ol class="legal-numbered">
<li>That the suit is not maintainable in present form for want of cause of action / jurisdiction.</li>
<li>That the plaint is vague, barred by limitation, and liable to be rejected in part.</li>
</ol>
<h2>Para-wise reply</h2>
<p><strong>Reply to para 1 of the plaint:</strong> The contents of para 1 are denied except to the extent specifically admitted herein.</p>
<p><strong>Reply to para 2 of the plaint:</strong> It is denied that the Defendant is liable as alleged. The true position is that ________.</p>
<h2>Additional pleadings</h2>
<p>The Defendant has performed its obligations and is ready to substantiate the same by documents on record.</p>
<h2>Prayer</h2>
<p>It is prayed that the suit be dismissed with costs in favour of the Defendant.</p>
<p>Verified at {{Venue}} on ________ that the contents of the above written statement are true to the best of my knowledge.</p>
`,
  reply: `
<h1 style="text-align:center">REPLY</h1>
<p><strong>Court:</strong> {{CourtName}} &nbsp; <strong>Case No.:</strong> {{CaseNumber}}</p>
<p><strong>Re:</strong> Reply on behalf of {{ClientName}} in matter {{MatterName}}</p>
<p>The Respondent most respectfully files this reply to the application / notice dated ________:</p>
<ol class="legal-numbered">
<li>That the allegations in the application are denied except as specifically admitted.</li>
<li>That the Respondent has complied with applicable law and is not in default.</li>
<li>That the relief sought is misconceived and liable to be dismissed.</li>
</ol>
<h2>Prayer</h2>
<p>It is prayed that the application be dismissed with costs.</p>
<p><strong>Place:</strong> {{Venue}} &nbsp; <strong>Date:</strong> ________</p>
`,
  bail_application: `
<h1 style="text-align:center">APPLICATION FOR BAIL</h1>
<p style="text-align:center"><strong>(Under Section 439 of the Code of Criminal Procedure, 1973)</strong></p>
<h2>IN THE COURT OF {{CourtName}}</h2>
<p><strong>Criminal Misc. Application No.:</strong> {{CaseNumber}}</p>
<p><strong>In the matter of:</strong> {{ClientName}} — Applicant / Accused</p>
<p><strong>Versus</strong></p>
<p>State of ________ — Respondent</p>
<p>Most respectfully sheweth:</p>
<ol class="legal-numbered">
<li>That the Applicant stands arrayed in FIR / Case No. {{CaseNumber}} registered at ________ for offences under ________.</li>
<li>That the Applicant was arrested on ________ and is in judicial custody / anticipatory custody is sought.</li>
<li>That the Applicant is innocent and has been falsely implicated; investigation is complete / custody is not required for investigation.</li>
<li>That the Applicant is a permanent resident of {{Address}} at {{Venue}}, has deep roots in the community, and is not a flight risk.</li>
<li>That the Applicant undertakes to abide by all conditions imposed by this Hon'ble Court and to appear on every date.</li>
<li>That co-accused, if any, have been enlarged on bail / parity may be considered.</li>
</ol>
<h2>Prayer</h2>
<p>It is therefore most respectfully prayed that this Hon'ble Court may be pleased to enlarge the Applicant on bail on such terms and conditions as deemed fit, including furnishing personal bond and surety.</p>
<p><strong>Place:</strong> {{Venue}} &nbsp; <strong>Date:</strong> ________</p>
<p><strong>Through Counsel for the Applicant</strong></p>
`,
  custom: `
<h1 style="text-align:center">DOCUMENT TITLE</h1>
<p style="text-align:center">{{MatterName}} · {{ClientName}}</p>
<h2>1. Background</h2>
<p></p>
<h2>2. Terms</h2>
<p></p>
<h2>3. General</h2>
<p>This document is governed by the laws of India. Courts at {{Venue}} shall have jurisdiction.</p>
${EXECUTION_BLOCK_HTML}
`,
};

export function getTemplateDefaultTitle(id: LegalTemplateId): string {
  const t = LEGAL_TEMPLATES.find((x) => x.id === id);
  return t ? t.label : "Untitled document";
}

export function applyMatterVariables(html: string, vars: Record<string, string>): string {
  let out = html;
  for (const [k, v] of Object.entries(vars)) {
    if (!v) continue;
    out = out.replaceAll(`{{${k}}}`, v);
    const pascal = k.charAt(0).toUpperCase() + k.slice(1);
    out = out.replaceAll(`{{${pascal}}}`, v);
  }
  return out.replace(/\{\{[A-Za-z0-9_]+\}\}/g, "________");
}

export function getLegalTemplateHtml(
  templateId: LegalTemplateId,
  vars: Record<string, string> = {}
): string {
  const raw = SKELETONS[templateId] || SKELETONS.custom;
  return applyMatterVariables(raw.trim(), vars);
}

export function isDocumentEmpty(html: string): boolean {
  const t = (html || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  if (!t) return true;
  if (t.length < 8) return true;
  return false;
}

export function hasPlaceholderSkeleton(html: string): boolean {
  return /\[Insert|\[Ground|\[Reply|\[Fact|\[Salary|\[Role|\[Chronological|\[Relief|\[Background|\[Breach|\[remedy|\[If any|\[Description|\[specify/i.test(
    html || ""
  );
}

export function countWordsFromHtml(html: string): number {
  const t = (html || "")
    .replace(/<br\s*\/?>/gi, " ")
    .replace(/<\/p>/gi, " ")
    .replace(/<\/td>/gi, " ")
    .replace(/<\/th>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!t) return 0;
  return t.split(" ").filter(Boolean).length;
}

export function estimatePages(wordCount: number): number {
  return Math.max(1, Math.ceil(wordCount / 350));
}
