const CLIENT = import.meta.env.VITE_ADSENSE_CLIENT;

/** Renders nothing until an AdSense client id is set, so ads never show in dev. */
export function AdSlot({ slot }: { slot: string }) {
  if (!CLIENT) return null;
  return (
    <ins
      className="adsbygoogle"
      style={{ display: "block" }}
      data-ad-client={CLIENT}
      data-ad-slot={slot}
      data-ad-format="auto"
      data-full-width-responsive="true"
    />
  );
}
