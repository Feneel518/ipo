export function QuietBoardIllustration({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 400 320" className={className} role="img" aria-hidden="true">
      <circle cx="235" cy="150" r="118" fill="var(--green-light)" opacity="0.55" />
      <line x1="40" y1="288" x2="360" y2="288" stroke="var(--ink)" strokeWidth="1.5" opacity="0.35" />

      <polygon points="182,232 150,288 160,288 190,236" fill="var(--ink)" />
      <polygon points="238,232 268,288 258,288 228,236" fill="var(--ink)" />

      <g transform="rotate(-3 210 150)">
        <rect x="140" y="55" width="150" height="180" fill="var(--white)" stroke="var(--ink)" strokeWidth="3" />
        <rect x="156" y="72" width="46" height="10" fill="var(--ink)" />
        <line x1="156" y1="104" x2="274" y2="104" stroke="var(--rule)" strokeWidth="2" />
        <line x1="156" y1="130" x2="274" y2="130" stroke="var(--rule)" strokeWidth="2" />
        <line x1="156" y1="156" x2="274" y2="156" stroke="var(--rule)" strokeWidth="2" />
        <line x1="156" y1="182" x2="274" y2="182" stroke="var(--rule)" strokeWidth="2" />
        <line x1="156" y1="208" x2="274" y2="208" stroke="var(--rule)" strokeWidth="2" />
      </g>

      <g transform="translate(58 180)">
        <polygon points="0,60 54,60 46,92 8,92" fill="var(--orange)" stroke="var(--ink)" strokeWidth="2.5" />
        <line x1="27" y1="60" x2="27" y2="20" stroke="var(--ink)" strokeWidth="2.5" />
        <polygon points="27,10 2,34 27,34" fill="var(--green)" stroke="var(--ink)" strokeWidth="2" />
        <polygon points="27,10 52,30 27,34" fill="var(--green-light)" stroke="var(--ink)" strokeWidth="2" />
        <circle cx="40" cy="12" r="12" fill="var(--orange-light)" stroke="var(--ink)" strokeWidth="2" />
        <path d="M35 7 h10 M38 7 v11 M35 12 h8" stroke="var(--ink)" strokeWidth="1.5" fill="none" strokeLinecap="round" />
      </g>

      <g transform="translate(300 150)">
        <circle cx="0" cy="0" r="16" fill="var(--orange-light)" stroke="var(--ink)" strokeWidth="2.5" />
        <polygon points="-15,18 15,18 20,80 -20,80" fill="var(--green)" stroke="var(--ink)" strokeWidth="2.5" />
        <line x1="-14" y1="80" x2="-18" y2="118" stroke="var(--ink)" strokeWidth="3" strokeLinecap="round" />
        <line x1="14" y1="80" x2="18" y2="118" stroke="var(--ink)" strokeWidth="3" strokeLinecap="round" />
        <path d="M14 30 L36 8" stroke="var(--ink)" strokeWidth="3" strokeLinecap="round" fill="none" />
        <circle cx="38" cy="6" r="4.5" fill="var(--ink)" />
        <line x1="-14" y1="34" x2="-24" y2="60" stroke="var(--ink)" strokeWidth="3" strokeLinecap="round" />
      </g>

      <path d="M330 70 l4 12 l12 4 l-12 4 l-4 12 l-4 -12 l-12 -4 l12 -4 z" fill="var(--orange)" />
      <path d="M100 96 l2.5 7 l7 2.5 l-7 2.5 l-2.5 7 l-2.5 -7 l-7 -2.5 l7 -2.5 z" fill="var(--green)" opacity="0.8" />
    </svg>
  );
}

export function EmptyRailIllustration({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 400 320" className={className} role="img" aria-hidden="true">
      <circle cx="190" cy="145" r="118" fill="var(--orange-light)" opacity="0.5" />
      <line x1="40" y1="288" x2="360" y2="288" stroke="var(--ink)" strokeWidth="1.5" opacity="0.35" />

      <g transform="rotate(2 200 150)">
        <rect x="130" y="60" width="150" height="170" fill="var(--white)" stroke="var(--ink)" strokeWidth="3" />
        <rect x="130" y="60" width="150" height="34" fill="var(--ink)" />
        <circle cx="160" cy="48" r="9" fill="none" stroke="var(--ink)" strokeWidth="3" />
        <circle cx="250" cy="48" r="9" fill="none" stroke="var(--ink)" strokeWidth="3" />
        <line x1="160" y1="60" x2="160" y2="40" stroke="var(--ink)" strokeWidth="3" />
        <line x1="250" y1="60" x2="250" y2="40" stroke="var(--ink)" strokeWidth="3" />
        <circle cx="155" cy="130" r="8" fill="none" stroke="var(--rule)" strokeWidth="2" />
        <circle cx="187" cy="130" r="8" fill="none" stroke="var(--rule)" strokeWidth="2" />
        <circle cx="219" cy="130" r="8" fill="none" stroke="var(--rule)" strokeWidth="2" />
        <circle cx="251" cy="130" r="8" fill="none" stroke="var(--rule)" strokeWidth="2" />
        <circle cx="155" cy="168" r="8" fill="none" stroke="var(--rule)" strokeWidth="2" />
        <circle cx="187" cy="168" r="8" fill="none" stroke="var(--rule)" strokeWidth="2" />
        <circle cx="219" cy="168" r="8" fill="none" stroke="var(--rule)" strokeWidth="2" />
        <circle cx="251" cy="168" r="8" fill="none" stroke="var(--rule)" strokeWidth="2" />
        <line x1="146" y1="200" x2="264" y2="200" strokeDasharray="4 6" stroke="var(--orange)" strokeWidth="2.5" />
      </g>

      <g transform="translate(85 165)">
        <circle cx="0" cy="0" r="15" fill="var(--green-light)" stroke="var(--ink)" strokeWidth="2.5" />
        <polygon points="-14,17 14,17 18,74 -18,74" fill="var(--orange)" stroke="var(--ink)" strokeWidth="2.5" />
        <line x1="-13" y1="74" x2="-17" y2="110" stroke="var(--ink)" strokeWidth="3" strokeLinecap="round" />
        <line x1="13" y1="74" x2="17" y2="110" stroke="var(--ink)" strokeWidth="3" strokeLinecap="round" />
        <line x1="13" y1="28" x2="34" y2="10" stroke="var(--ink)" strokeWidth="3" strokeLinecap="round" />
        <circle cx="46" cy="-2" r="13" fill="none" stroke="var(--ink)" strokeWidth="3" />
        <line x1="55" y1="7" x2="66" y2="18" stroke="var(--ink)" strokeWidth="3.5" strokeLinecap="round" />
      </g>

      <path d="M310 100 l3.5 10 l10 3.5 l-10 3.5 l-3.5 10 l-3.5 -10 l-10 -3.5 l10 -3.5 z" fill="var(--orange)" />
      <path d="M300 210 l2.5 7 l7 2.5 l-7 2.5 l-2.5 7 l-2.5 -7 l-7 -2.5 l7 -2.5 z" fill="var(--green)" opacity="0.85" />
    </svg>
  );
}

export function NotFoundIllustration({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 400 320" className={className} role="img" aria-hidden="true">
      <circle cx="205" cy="150" r="120" fill="var(--orange-light)" opacity="0.55" />
      <line x1="40" y1="288" x2="360" y2="288" stroke="var(--ink)" strokeWidth="1.5" opacity="0.35" />

      <g transform="rotate(-2 200 150)">
        <path d="M140 60 H290 V230 H140 Z M255 60 L290 95 H255 Z" fill="var(--white)" stroke="var(--ink)" strokeWidth="3" strokeLinejoin="round" />
        <line x1="156" y1="112" x2="240" y2="112" stroke="var(--rule)" strokeWidth="2" />
        <line x1="156" y1="140" x2="240" y2="140" stroke="var(--rule)" strokeWidth="2" />
        <line x1="156" y1="168" x2="274" y2="168" stroke="var(--rule)" strokeWidth="2" />
        <line x1="156" y1="196" x2="274" y2="196" stroke="var(--rule)" strokeWidth="2" />
      </g>

      <g transform="rotate(18 330 60)">
        <rect x="300" y="35" width="60" height="42" fill="var(--paper)" stroke="var(--ink)" strokeWidth="2.5" />
        <circle cx="345" cy="66" r="7" fill="var(--orange)" stroke="var(--ink)" strokeWidth="1.5" />
        <line x1="309" y1="47" x2="335" y2="47" stroke="var(--ink)" strokeWidth="2" />
        <line x1="309" y1="56" x2="330" y2="56" stroke="var(--ink)" strokeWidth="2" />
      </g>
      <path d="M292 78 q-10 -4 -18 -2" stroke="var(--ink)" strokeWidth="2" fill="none" strokeLinecap="round" opacity="0.5" />
      <path d="M286 90 q-10 -2 -16 2" stroke="var(--ink)" strokeWidth="2" fill="none" strokeLinecap="round" opacity="0.35" />

      <g transform="translate(95 175)">
        <circle cx="0" cy="0" r="16" fill="var(--green-light)" stroke="var(--ink)" strokeWidth="2.5" />
        <line x1="-6" y1="-3" x2="-2" y2="-3" stroke="var(--ink)" strokeWidth="2" strokeLinecap="round" />
        <line x1="2" y1="-3" x2="6" y2="-3" stroke="var(--ink)" strokeWidth="2" strokeLinecap="round" />
        <path d="M-5 6 q5 4 10 0" stroke="var(--ink)" strokeWidth="2" fill="none" strokeLinecap="round" />
        <polygon points="-15,18 15,18 20,76 -20,76" fill="var(--orange)" stroke="var(--ink)" strokeWidth="2.5" />
        <line x1="-14" y1="76" x2="-18" y2="112" stroke="var(--ink)" strokeWidth="3" strokeLinecap="round" />
        <line x1="14" y1="76" x2="18" y2="112" stroke="var(--ink)" strokeWidth="3" strokeLinecap="round" />
        <path d="M-14 30 q-22 -6 -26 10" stroke="var(--ink)" strokeWidth="3" fill="none" strokeLinecap="round" />
        <path d="M14 30 q22 -6 26 10" stroke="var(--ink)" strokeWidth="3" fill="none" strokeLinecap="round" />
      </g>

      <path d="M320 210 l3.5 10 l10 3.5 l-10 3.5 l-3.5 10 l-3.5 -10 l-10 -3.5 l10 -3.5 z" fill="var(--green)" opacity="0.85" />
    </svg>
  );
}

export function ListingBellIllustration({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 280 260" className={className} role="img" aria-hidden="true">
      <circle cx="140" cy="115" r="95" fill="var(--green-light)" opacity="0.5" />
      <line x1="25" y1="215" x2="255" y2="215" stroke="var(--ink)" strokeWidth="1.5" opacity="0.35" />

      <rect x="40" y="175" width="26" height="40" fill="var(--white)" stroke="var(--ink)" strokeWidth="2.5" />
      <rect x="74" y="145" width="26" height="70" fill="var(--orange-light)" stroke="var(--ink)" strokeWidth="2.5" />
      <rect x="108" y="100" width="26" height="115" fill="var(--orange)" stroke="var(--ink)" strokeWidth="2.5" />

      <path d="M53 172 L87 138 L121 96 L150 62" stroke="var(--ink)" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M136 70 L150 62 L146 78" stroke="var(--ink)" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M168 45 l3.5 10 l10 3.5 l-10 3.5 l-3.5 10 l-3.5 -10 l-10 -3.5 l10 -3.5 z" fill="var(--green)" />

      <line x1="175" y1="215" x2="175" y2="110" stroke="var(--ink)" strokeWidth="4" strokeLinecap="round" />
      <line x1="175" y1="110" x2="215" y2="110" stroke="var(--ink)" strokeWidth="4" strokeLinecap="round" />
      <line x1="175" y1="160" x2="200" y2="140" stroke="var(--ink)" strokeWidth="2.5" strokeLinecap="round" />
      <line x1="210" y1="121" x2="210" y2="128" stroke="var(--ink)" strokeWidth="2.5" />
      <circle cx="210" cy="116" r="5" fill="none" stroke="var(--ink)" strokeWidth="2.5" />

      <path d="M190 128 C190 108 230 108 230 128 L236 168 C236 176 184 176 184 168 Z" fill="var(--orange)" stroke="var(--ink)" strokeWidth="2.5" strokeLinejoin="round" />
      <ellipse cx="200" cy="132" rx="6" ry="10" fill="var(--orange-light)" opacity="0.6" />
      <rect x="182" y="168" width="56" height="9" fill="var(--ink)" />
      <circle cx="210" cy="186" r="6" fill="var(--ink)" />

      <path d="M250 90 l3 8 l8 3 l-8 3 l-3 8 l-3 -8 l-8 -3 l8 -3 z" fill="var(--green)" />
      <circle cx="170" cy="100" r="4" fill="var(--orange)" />
      <path d="M245 150 l2.5 7 l7 2.5 l-7 2.5 l-2.5 7 l-2.5 -7 l-7 -2.5 l7 -2.5 z" fill="var(--orange)" opacity="0.85" />
    </svg>
  );
}
