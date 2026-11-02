// Inline stroke icons (no emoji, no icon font).
import type { ReactElement } from 'react';

const S = ({ d }: { d: ReactElement }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">{d}</svg>
);
export const I = {
  mark: (
    <svg viewBox="0 0 32 32" fill="none"><circle cx="16" cy="16" r="15" fill="#000D4C" />
      <path d="M7 19c2.2 0 2.2-1.6 4.5-1.6S13.8 19 16 19s2.2-1.6 4.5-1.6S22.8 19 25 19" stroke="#2AA8F2" strokeWidth="2" strokeLinecap="round" />
      <path d="M7 23c2.2 0 2.2-1.6 4.5-1.6S13.8 23 16 23s2.2-1.6 4.5-1.6S22.8 23 25 23" stroke="#fff" strokeWidth="2" strokeLinecap="round" opacity=".55" />
      <circle cx="16" cy="11" r="3.2" fill="#3C45E6" stroke="#fff" strokeWidth="1.6" /></svg>
  ),
  review: <S d={<><path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z" /><path d="M14 3v5h5" /><path d="M9 14l2 2 4-4" /></>} />,
  deal: <S d={<><path d="M4 6h16v10H8l-4 4z" /><path d="M8 10h8M8 13h5" /></>} />,
  ship: <S d={<><path d="M3 17l2 4h14l2-4z" /><path d="M5 17V9h14v8" /><path d="M9 9V5h6v4" /><path d="M12 5V3" /></>} />,
  assistant: <S d={<><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="3.5" fill="currentColor" /></>} />,
  page: <S d={<><path d="M14 3H6v18h12V7z" /><path d="M14 3v4h4" /></>} />,
  check: <S d={<path d="M5 12l4 4 10-10" />} />,
  alert: <S d={<><path d="M12 3l9.5 17h-19z" /><path d="M12 10v4M12 17.5v.01" /></>} />,
  send: <S d={<path d="M4 12l16-8-6 16-3-7z" />} />,
  copy: <S d={<><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3" /></>} />,
  save: <S d={<><path d="M5 3h11l3 3v15H5z" /><path d="M8 3v5h8V3M8 21v-7h8v7" /></>} />,
  back: <S d={<path d="M15 6l-6 6 6 6" />} />,
  bank: <S d={<><path d="M3 10l9-6 9 6" /><path d="M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 21h18" /></>} />,
  spark: <S d={<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6" />} />,
  clock: <S d={<><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>} />,
  euro: <S d={<><path d="M17 6a7 7 0 1 0 0 12" /><path d="M4 10h9M4 14h9" /></>} />,
  plus: <S d={<path d="M12 5v14M5 12h14" />} />,
  trash: <S d={<><path d="M4 7h16M10 11v6M14 11v6" /><path d="M6 7l1 13h10l1-13M9 7V4h6v3" /></>} />,
};
