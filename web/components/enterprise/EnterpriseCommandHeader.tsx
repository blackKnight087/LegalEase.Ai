"use client";

import EnterpriseGlobalSearch from "@/components/enterprise/EnterpriseGlobalSearch";
import EnterpriseNotifications from "@/components/enterprise/EnterpriseNotifications";
import { useApiConnection } from "@/components/providers/ApiConnectionProvider";
import type { EnterpriseModule, NotificationItem } from "@/lib/enterpriseWorkspace";

function StatusPill({ label, active }: { label: string; active: boolean }) {
  return (
    <span className="ent-command-header__status" title={label}>
      <span
        className={`ent-command-header__status-dot ${active ? "is-on" : ""}`}
        aria-hidden
      />
      <span className="ent-command-header__status-label">{label}</span>
    </span>
  );
}

export default function EnterpriseCommandHeader({
  notifications,
  onNavigate,
  onSelectMatter,
}: {
  notifications: NotificationItem[];
  onNavigate: (m: EnterpriseModule) => void;
  onSelectMatter?: (matterId: string) => void;
}) {
  const { apiOnline, llmOnline } = useApiConnection();

  return (
    <header className="ent-command-header shrink-0">
      <div className="ent-command-header__pattern" aria-hidden />
      <div className="ent-command-header__inner">
        <div className="ent-command-header__brand">
          <p className="ent-command-header__eyebrow m-0 hidden sm:block">LegalEase.AI · Firm OS</p>
          <h1 className="ent-command-header__title m-0">Enterprise</h1>
          <p className="ent-command-header__subtitle m-0">Firm command center</p>
        </div>

        <div className="ent-command-header__search">
          <EnterpriseGlobalSearch
            inHeader
            onNavigate={onNavigate}
            onSelectMatter={onSelectMatter}
          />
        </div>

        <div className="ent-command-header__actions">
          <div className="ent-command-header__status-group hidden md:flex">
            <StatusPill label="API Connected" active={apiOnline} />
            <StatusPill label="AI Active" active={llmOnline} />
            <StatusPill label="Court Sync Ready" active={apiOnline} />
          </div>
          <EnterpriseNotifications items={notifications} inHeader />
        </div>
      </div>

      <div className="ent-command-header__status-mobile md:hidden">
        <StatusPill label="API Connected" active={apiOnline} />
        <StatusPill label="AI Active" active={llmOnline} />
        <StatusPill label="Court Sync Ready" active={apiOnline} />
      </div>
    </header>
  );
}
