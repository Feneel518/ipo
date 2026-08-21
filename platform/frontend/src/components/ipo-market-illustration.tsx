import Image from "next/image";

export function IpoMarketIllustration({ className }: { className?: string }) {
  return (
    <Image
      className={className}
      src="/illustrations/ipo-market-illustration.svg"
      alt=""
      width={840}
      height={793}
      unoptimized
      aria-hidden="true"
    />
  );
}
