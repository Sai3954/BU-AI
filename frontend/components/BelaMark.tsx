/** Ask Bela mark: B in a flame inside a chat bubble. Below 24px the bubble and B are dropped so it stays crisp. */
const FLAME = "M64 30C75 44 88 54 86 74 84 90 74 98 64 98 54 98 43 90 42 75 41 61 50 55 52 45 56 53 59 55 61 51 63 44 61 37 64 30Z";
const BUBBLE = "M64 22a42 42 0 1 1-26 75l-14 6 5-14A42 42 0 0 1 64 22z";
const B = "M74.37 84.33Q74.37 87.51 71.98 89.26Q69.59 91 65.34 91H53.63V67.61H64.34Q68.62 67.61 70.82 69.09Q73.02 70.58 73.02 73.49Q73.02 75.48 71.92 76.85Q70.81 78.22 68.56 78.7Q71.4 79.03 72.88 80.48Q74.37 81.94 74.37 84.33ZM68.09 74.15Q68.09 72.57 67.09 71.91Q66.08 71.24 64.11 71.24H58.53V77.04H64.14Q66.22 77.04 67.15 76.32Q68.09 75.59 68.09 74.15ZM69.45 83.94Q69.45 80.66 64.74 80.66H58.53V87.36H64.92Q67.28 87.36 68.37 86.51Q69.45 85.65 69.45 83.94Z";
const B_SMALL = "M75.59 84.54Q75.59 88.1 72.92 90.05Q70.24 92 65.49 92H52.41V65.86H64.38Q69.17 65.86 71.63 67.52Q74.08 69.18 74.08 72.42Q74.08 74.65 72.85 76.18Q71.62 77.71 69.09 78.25Q72.27 78.62 73.93 80.25Q75.59 81.87 75.59 84.54ZM68.57 73.17Q68.57 71.4 67.45 70.66Q66.33 69.92 64.12 69.92H57.89V76.4H64.16Q66.48 76.4 67.53 75.59Q68.57 74.78 68.57 73.17ZM70.1 84.11Q70.1 80.44 64.83 80.44H57.89V87.94H65.03Q67.66 87.94 68.88 86.98Q70.1 86.03 70.1 84.11Z";
const TINY_FLAME = "M64 18C80 40 98 55 96 81 94 102 79 112 64 112 49 112 33 102 32 83 31 64 45 56 47 43 53 54 58 56 60 49 62 39 60 30 64 18Z";

export function BelaMark({ size = 40, className = "" }: { size?: number; className?: string }) {
  const small = size < 48;
  return (
    <svg className={`bela-mark ${className}`} width={size} height={size} viewBox="0 0 128 128" aria-hidden="true" focusable="false">
      <circle cx="64" cy="64" r="62" fill="#123D35" />
      {size < 24 ? <path d={TINY_FLAME} fill="#EFA31A" /> : <>
        <path d={BUBBLE} fill="none" stroke="#FFFFFF" strokeWidth={small ? 9 : 6} strokeLinejoin="round" />
        <path d={FLAME} fill="#EFA31A" />
        <path d={small ? B_SMALL : B} fill="#123D35" />
      </>}
    </svg>
  );
}

/** Gold three-star AI sparkle shown after the name; it twinkles while Bela is thinking. */
export function Sparkle({ size = 18, active = false }: { size?: number; active?: boolean }) {
  return (
    <svg className={`sparkle${active ? " on" : ""}`} width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path className="s1" d="M10 3l1.6 4.4L16 9l-4.4 1.6L10 15l-1.6-4.4L4 9l4.4-1.6z" fill="#EFA31A" />
      <path className="s2" d="M18 2l.8 2.2L21 5l-2.2.8L18 8l-.8-2.2L15 5l2.2-.8z" fill="#EFA31A" />
      <path className="s3" d="M18 14l.8 2.2L21 17l-2.2.8L18 20l-.8-2.2L15 17l2.2-.8z" fill="#EFA31A" />
    </svg>
  );
}
