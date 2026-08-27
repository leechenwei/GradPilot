type Props = { value: number; caption: string }

export default function FitMeter({ value, caption }: Props) {
  const tone = value >= 75 ? 'strong' : value >= 50 ? 'fair' : 'weak'
  return (
    <div className="fit">
      <div className={`fit__ring fit__ring--${tone}`} style={{ '--value': value } as React.CSSProperties}>
        <span>{value}%</span>
      </div>
      <p className="fit__caption">{caption}</p>
    </div>
  )
}
