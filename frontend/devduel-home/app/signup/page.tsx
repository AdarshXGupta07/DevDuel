"use client";

import MouseParallaxBG from "../components/MouseParallaxBG";
import Link from "next/link";

export default function SignupPage() {
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
          href="/login"
          className="
            px-6 py-2.5 rounded-full
            bg-indigo-500/30
            backdrop-blur-[8px]
            border border-indigo-400/50
            hover:bg-indigo-500/45
            transition
          "
        >
          Login
        </Link>
      </nav>

      {/* Signup Card */}
      <section className="relative z-10 flex items-center justify-center px-6 py-14">
        <div
          className="
            w-full max-w-4xl
            rounded-[72px]
            px-24 py-24
            bg-white/10
            backdrop-blur-[18px]
            border border-white/30
            shadow-[0_40px_120px_rgba(0,0,0,0.55)]
          "
        >
          {/* Header */}
          <div className="text-center mb-16">
            <h2 className="text-4xl font-extrabold mb-4">
              Join the Arena
            </h2>
            <p className="text-white/75 text-lg">
              Create your DevDuel account
            </p>
          </div>

          {/* Form */}
          <form className="mx-auto max-w-2xl flex flex-col gap-10">
            {/* Username */}
            <input
              type="text"
              placeholder="Username"
              className="
                h-[72px]
                px-10
                rounded-full
                bg-black/30
                backdrop-blur-[8px]
                border border-white/25
                text-xl text-white
                placeholder-white/60
                focus:outline-none
                focus:border-indigo-400/70
                transition
              "
            />

            {/* Email */}
            <input
              type="email"
              placeholder="Email"
              className="
                h-[72px]
                px-10
                rounded-full
                bg-black/30
                backdrop-blur-[8px]
                border border-white/25
                text-xl text-white
                placeholder-white/60
                focus:outline-none
                focus:border-indigo-400/70
                transition
              "
            />

            {/* Password */}
            <input
              type="password"
              placeholder="Password"
              className="
                h-[72px]
                px-10
                rounded-full
                bg-black/30
                backdrop-blur-[8px]
                border border-white/25
                text-xl text-white
                placeholder-white/60
                focus:outline-none
                focus:border-indigo-400/70
                transition
              "
            />

            {/* Button */}
            <button
              type="submit"
              className="
                mt-6
                h-[72px]
                rounded-full
                text-xl font-semibold
                bg-indigo-500/35
                backdrop-blur-[14px]
                border border-indigo-400/60
                shadow-[0_0_55px_rgba(99,102,241,0.55)]
                hover:bg-indigo-500/50
                hover:scale-[1.04]
                transition
              "
            >
              Sign Up 🚀
            </button>
          </form>

          {/* Footer */}
          <p className="mt-18 text-center text-white/70 text-lg">
            Already have an account?{" "}
            <Link href="/login" className="text-indigo-400 hover:underline">
              Login
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
