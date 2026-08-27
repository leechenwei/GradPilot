import { useEffect, useRef } from 'react'

const CLIENT = import.meta.env.VITE_ADSENSE_CLIENT

type Props = { slot: string; label?: string }

/**
 * Renders an AdSense unit, or nothing at all when no client id is configured.
 * Keeping the no-op path first means development and screenshots stay ad-free.
 */
export default function AdSlot({ slot, label = 'Advertisement' }: Props) {
  const pushed = useRef(false)

  useEffect(() => {
    if (!CLIENT || pushed.current) return
    pushed.current = true
    const win = window as unknown as { adsbygoogle?: unknown[] }
    win.adsbygoogle = win.adsbygoogle ?? []
    win.adsbygoogle.push({})
  }, [])

  if (!CLIENT) return null

  return (
    <aside className="ad-slot" aria-label={label}>
      <span className="ad-slot__label">{label}</span>
      <ins
        className="adsbygoogle"
        style={{ display: 'block' }}
        data-ad-client={CLIENT}
        data-ad-slot={slot}
        data-ad-format="auto"
        data-full-width-responsive="true"
      />
    </aside>
  )
}
