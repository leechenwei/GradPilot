/** Lucide paths inlined. One icon set, 1.75 stroke, 20px box — no icon dependency. */
type Props = { className?: string };

function Svg({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export const ScoutIcon = (p: Props) => (
  <Svg {...p}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></Svg>
);
export const MatcherIcon = (p: Props) => (
  <Svg {...p}><path d="M3 12h4l3 8 4-16 3 8h4" /></Svg>
);
export const WriterIcon = (p: Props) => (
  <Svg {...p}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></Svg>
);
export const CriticIcon = (p: Props) => (
  <Svg {...p}><path d="m3 6 3 3 3-3" /><path d="M6 9V5a2 2 0 0 1 2-2h9" /><path d="m21 18-3-3-3 3" /><path d="M18 15v4a2 2 0 0 1-2 2H7" /></Svg>
);
export const InterviewerIcon = (p: Props) => (
  <Svg {...p}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z" /></Svg>
);
export const CheckIcon = (p: Props) => <Svg {...p}><path d="M20 6 9 17l-5-5" /></Svg>;
export const CopyIcon = (p: Props) => (
  <Svg {...p}><rect x="9" y="9" width="12" height="12" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h10" /></Svg>
);
export const AlertIcon = (p: Props) => (
  <Svg {...p}><circle cx="12" cy="12" r="9" /><path d="M12 8v5" /><path d="M12 16h.01" /></Svg>
);
export const SparkIcon = (p: Props) => (
  <Svg {...p}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18" /></Svg>
);
export const LinkIcon = (p: Props) => (
  <Svg {...p}><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1" /><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" /></Svg>
);
export const UploadIcon = (p: Props) => (
  <Svg {...p}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><path d="m7 9 5-5 5 5" /><path d="M12 4v12" /></Svg>
);
