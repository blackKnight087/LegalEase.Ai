/** Avoid static path generation — matter timeline is always dynamic. */
export const dynamic = "force-dynamic";
export const dynamicParams = true;

export default function MatterTimelineLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
