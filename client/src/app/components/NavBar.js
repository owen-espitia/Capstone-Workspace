"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

export default function NavBar() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState(undefined); // undefined = loading, null = anon

  useEffect(() => {
    // The navbar lives in the root layout and stays mounted across navigation,
    // so re-check the session whenever the route changes (e.g. after login).
    fetch("/api/auth/me", { credentials: "include", cache: "no-store" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => setUser(data?.user ?? null))
      .catch(() => setUser(null));
  }, [pathname]);

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    setUser(null);
    router.push("/");
    router.refresh();
  }

  return (
    <nav className="border-b border-ink bg-paper">
      <div className="mx-auto flex max-w-5xl items-center gap-8 px-8 py-4">
        <Link href="/" className="font-display text-2xl font-medium uppercase tracking-wider">
          SockCheck<span className="text-brand">.ai</span>
        </Link>
        <Link href="/upload" className="eyebrow hover:text-brand">
          Upload Image
        </Link>

        <div className="ml-auto flex items-center gap-3">
          {user === undefined ? null : user ? (
            <>
              <span className="eyebrow">{user.name || user.email}</span>
              <button onClick={handleLogout} className="btn btn-ghost">
                Log out
              </button>
            </>
          ) : (
            <>
              <Link href="/login" className="btn btn-ghost">
                Sign in
              </Link>
              <Link href="/register" className="btn btn-primary">
                Register
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
