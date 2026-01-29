"use client";

import { useEffect, useState } from "react";

export default function MouseParallaxBG() {
  const [pos, setPos] = useState({ x: 50, y: 50 });
  const [pulse, setPulse] = useState(0);

  // Cursor spotlight
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      setPos({
        x: (e.clientX / window.innerWidth) * 100,
        y: (e.clientY / window.innerHeight) * 100,
      });
    };
    window.addEventListener("mousemove", onMove);
    return () => window.removeEventListener("mousemove", onMove);
  }, []);

  // Breathing + neon pulse
  useEffect(() => {
    let t = 0;
    const loop = () => {
      t += 0.015;
      setPulse((Math.sin(t) + 1) / 2); // 0 → 1
      requestAnimationFrame(loop);
    };
    loop();
  }, []);

  const glowStrength = 0.25 + pulse * 0.15;
  const scale = 1 + pulse * 0.02;

  return (
    <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden">
      {/* Breathing glow layer */}
      <div
        className="absolute inset-0 transition-transform duration-1000"
        style={{
          transform: `scale(${scale})`,
          background: `
            radial-gradient(
              circle at ${pos.x}% ${pos.y}%,
              rgba(99,102,241,${glowStrength}),
              transparent 45%
            ),
            radial-gradient(
              circle at ${100 - pos.x}% ${100 - pos.y}%,
              rgba(168,85,247,${glowStrength}),
              transparent 50%
            ),
            #000
          `,
        }}
      />

      {/* Neon grid */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage: `
            linear-gradient(
              to right,
              rgba(99,102,241,${0.08 + pulse * 0.05}) 1px,
              transparent 1px
            ),
            linear-gradient(
              to bottom,
              rgba(99,102,241,${0.08 + pulse * 0.05}) 1px,
              transparent 1px
            )
          `,
          backgroundSize: "60px 60px",
        }}
      />
    </div>
  );
}
