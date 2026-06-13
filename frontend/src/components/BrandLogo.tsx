/**
 * Amisys QHSE brand mark: orange "A" arch with three network nodes,
 * recreated as inline SVG from the partner's identity asset.
 * Colour defaults to the brand orange token; pass `color` to override.
 */
export function BrandLogo({ size = 30, color = 'var(--brand-orange)' }: { size?: number; color?: string }) {
  return (
    <svg
      className="brand-logo"
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      stroke={color}
      strokeWidth="2.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {/* outer arch of the A */}
      <path d="M7 23.4 V13.2 Q7 6.8 13.4 6.8 H18.6 Q25 6.8 25 13.2 V23.4" />
      {/* centre node */}
      <circle cx="16" cy="16.4" r="2.6" />
      {/* inner legs from centre node to foot nodes */}
      <path d="M14.4 18.6 L9 24.1" />
      <path d="M17.6 18.6 L23 24.1" />
      {/* foot nodes */}
      <circle cx="7" cy="26.3" r="2.8" />
      <circle cx="25" cy="26.3" r="2.8" />
    </svg>
  );
}
