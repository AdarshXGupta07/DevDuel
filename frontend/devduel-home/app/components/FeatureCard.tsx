"use client";

import { useState } from "react";

type Props = {
  title: string;
  desc: string;
  index: number;
};

export default function FeatureCard({ title, desc, index }: Props) {
  const [active, setActive] = useState<number | null>(null);
  const isActive = active === index;

  const shift =
    active === null ? 0 : index < active ? -120 : index > active ? 120 : 0;

  return (
    <div
      onMouseEnter={() => setActive(index)}
      onMouseLeave={() => setActive(null)}
      style={{
        transform: `translateX(${shift}px) scale(${isActive ? 1.05 : 1})`,
        opacity: active !== null && !isActive ? 0.6 : 1,
        backgroundColor: "rgba(255, 255, 255, 0.15)",
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
      }}
      className="
        w-80
        rounded-[50px]
        p-6
        border border-white/30
        shadow-[0_8px_30px_rgba(0,0,0,0.25)]
        transition-all duration-300 ease-out
        cursor-pointer
      "
    >
      <h3 className="text-xl font-semibold mb-3">{title}</h3>
      <p className="text-white/90 leading-relaxed">{desc}</p>
    </div>
  );
}
