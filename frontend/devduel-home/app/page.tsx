"use client";

import FeatureCard from "./components/FeatureCard";
import MouseParallaxBG from "./components/MouseParallaxBG";

export default function Home() {
  return (
    <main className="relative min-h-screen overflow-hidden text-white">
      {/* Background */}
      <MouseParallaxBG />

      {/* NAVBAR */}
      <nav className="relative z-10 flex justify-between items-center px-10 py-6">
        <h1 className="text-3xl font-bold tracking-wide">
          Dev<span className="text-indigo-400">Duel</span> AI
        </h1>

        <div className="flex gap-4">
          {/* Login */}
          <a
            href="/login"
            className="
              px-5 py-2 rounded-full
              bg-white/10
              backdrop-blur-[8px]
              border border-white/30
              text-white/90
              hover:bg-white/20
              transition
            "
          >
            Login
          </a>

          {/* Sign Up */}
          <a
            href="/signup"
            className="
              px-5 py-2 rounded-full
              bg-indigo-500/30
              backdrop-blur-[8px]
              border border-indigo-400/50
              text-white font-medium
              shadow-[0_0_20px_rgba(99,102,241,0.35)]
              hover:bg-indigo-500/45
              transition
            "
          >
            Sign Up
          </a>
        </div>
      </nav>

      {/* HERO */}
      <section className="relative z-10 flex flex-col items-center text-center px-6 pt-32 pb-32">
        <h2 className="text-6xl font-extrabold leading-tight">
          Code. Compete.
          <br />
          <span className="text-indigo-400">Dominate.</span>
        </h2>

        <p className="mt-6 max-w-2xl text-white/80 text-lg">
          AI-powered real-time coding duels with intelligent evaluation,
          adaptive difficulty, and skill-based rankings.
        </p>

        <div className="mt-10 flex gap-6">
          {/* Enter Arena */}
          <a
            href="/signup"
            className="
              px-10 py-4 rounded-full
              text-lg font-semibold text-white
              bg-indigo-500/35
              backdrop-blur-[10px]
              border border-indigo-400/60
              shadow-[0_0_40px_rgba(99,102,241,0.45)]
              hover:bg-indigo-500/50
              hover:scale-[1.03]
              transition
            "
          >
            Enter Arena ⚔️
          </a>

          {/* Secondary */}
          <a
            href="#features"
            className="
              px-8 py-4 rounded-full
              bg-white/10
              backdrop-blur-[8px]
              border border-white/25
              text-white/80
              hover:bg-white/20
              transition
            "
          >
            See How It Works
          </a>
        </div>
      </section>

      {/* FEATURES */}
      <section
        id="features"
        className="relative z-10 max-w-6xl mx-auto px-8 pb-32 flex gap-8 justify-center"
      >
        <FeatureCard
          index={0}
          title="⚔️ Real-Time Duels"
          desc="Low-latency 1v1 coding battles using WebSockets."
        />
        <FeatureCard
          index={1}
          title="🤖 AI Code Intelligence"
          desc="Complexity analysis, quality scoring, and optimization hints."
        />
        <FeatureCard
          index={2}
          title="📊 Skill-Based Ranking"
          desc="ELO-driven ratings that truly reflect developer skill."
        />
      </section>

      {/* FOOTER */}
      <footer className="relative z-10 text-center text-white/50 pb-6">
        © 2026 DevDuel AI • Built for Hackathons
      </footer>
    </main>
  );
}
