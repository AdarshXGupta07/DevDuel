"use client";

import MouseParallaxBG from "../components/MouseParallaxBG";
import Link from "next/link";

export default function LoginPage() {
  return (
    <main className="relative min-h-screen overflow-hidden text-white">
      {/* Background */}
      <MouseParallaxBG />

      {/* Navbar */}
      <nav className="relative z-10 flex justify-between items-center px-10 py-6">
        <h1 className="text-3xl font-bold tracking-wide">
          Dev<span className="text-indigo-400">Duel</span> AI
        </h1>

        <Link
          href="/signup"
          className="
            px-5 py-2 rounded-full
            bg-indigo-500/30
            backdrop-blur-[8px]
            border border-indigo-400/50
            shadow-[0_0_20px_rgba(99,102,241,0.35)]
            hover:bg-indigo-500/45
            transition
          "
        >
          Sign Up
        </Link>
      </nav>

      {/* Login Card */}
      <section className="relative z-10 flex items-center justify-center px-6 py-12">
        <div
          className="
            w-full max-w-4xl
            rounded-[70px]
            px-20 py-20
            bg-white/10
            backdrop-blur-[18px]
            border border-white/30
            shadow-[0_40px_120px_rgba(0,0,0,0.55)]
          "
        >
          {/* Header */}
          <div className="text-center mb-14">
            <h2 className="text-4xl font-extrabold mb-4">
              Welcome Back
            </h2>
            <p className="text-white/75 text-lg">
              Log in to enter the arena
            </p>
          </div>

          {/* Form Wrapper */}
          <form className="mx-auto max-w-xl flex flex-col gap-8">
            <input
              type="email"
              placeholder="Email"
              className="
                h-18 px-8 py-5 rounded-full
                bg-black/30
                backdrop-blur-[8px]
                border border-white/25
                text-lg text-white
                placeholder-white/60
                focus:outline-none
                focus:border-indigo-400/70
              "
            />

            <input
              type="password"
              placeholder="Password"
              className="
                h-18 px-8 py-5 rounded-full
                bg-black/30
                backdrop-blur-[8px]
                border border-white/25
                text-lg text-white
                placeholder-white/60
                focus:outline-none
                focus:border-indigo-400/70
              "
            />

            <button
              type="submit"
              className="
                mt-4 h-18 rounded-full
                text-lg font-semibold
                bg-indigo-500/35
                backdrop-blur-[14px]
                border border-indigo-400/60
                shadow-[0_0_50px_rgba(99,102,241,0.5)]
                hover:bg-indigo-500/50
                hover:scale-[1.04]
                transition
              "
            >
              Login ⚔️
            </button>
          </form>

          {/* Footer */}
          <p className="mt-16 text-center text-white/70 text-base">
            Don’t have an account?{" "}
            <Link href="/signup" className="text-indigo-400 hover:underline">
              Sign up
            </Link>
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 text-center text-white/50 pb-6">
        © 2026 DevDuel AI • Built for Hackathons
      </footer>
    </main>
  );
}
