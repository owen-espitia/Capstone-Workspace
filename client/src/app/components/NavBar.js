"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export default function NavBar() {
  const router = useRouter();
  const [user, setUser] = useState(undefined); // undefined = loading, null = anon

  useEffect(() => {
    fetch("/api/auth/me", { credentials: "include" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => setUser(data?.user ?? null))
      .catch(() => setUser(null));
  }, []);

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    setUser(null);
    router.push("/");
    router.refresh();
  }

  return (
    <nav className="border-b border-zinc-200 bg-white dark:bg-zinc-950 dark:border-zinc-800">
      <div className="mx-auto flex max-w-4xl items-center gap-6 px-8 py-4">
        <Link href="/" className="bg-cyan-950 border-2 border-solid rounded-md px-10 text-white">
          Home
        </Link>
        <Link href="/upload" className="bg-cyan-950 border-2 border-solid rounded-md px-10 text-white">
          Upload Image
        </Link>

        <div className="ml-auto flex items-center gap-4">
          {user === undefined ? null : user ? (
            <>
              <span className="text-sm text-zinc-600 dark:text-zinc-400">
                {user.email}
              </span>
              <button
                onClick={handleLogout}
                className="rounded-md border border-zinc-300 px-4 py-1 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                Sign out
              </button>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className="rounded-md border border-zinc-300 px-4 py-1 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                Sign in
              </Link>
              <Link
                href="/register"
                className="rounded-md bg-cyan-950 px-4 py-1 text-sm text-white hover:bg-cyan-900"
              >
                Register
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
