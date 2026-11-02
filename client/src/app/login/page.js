"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [form, setForm] = useState({ user_email: "", password: "" });
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  function handleChange(e) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
        credentials: "include",
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Login failed");
      router.push("/upload");
      router.refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col gap-8 px-6 py-16">
      <div>
        <h1 className="text-5xl">Sign in</h1>
        <p className="mt-2 text-sm">
          Don&apos;t have an account?{" "}
          <Link href="/register" className="text-brand underline underline-offset-4">
            Create one
          </Link>
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <label htmlFor="user_email" className="label">Email</label>
          <input
            id="user_email"
            name="user_email"
            type="email"
            required
            autoComplete="email"
            value={form.user_email}
            onChange={handleChange}
            className="field"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="password" className="label">Password</label>
          <input
            id="password"
            name="password"
            type="password"
            required
            autoComplete="current-password"
            value={form.password}
            onChange={handleChange}
            className="field"
          />
        </div>

        {error && (
          <p role="alert" className="alert-error">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="btn btn-primary py-3"
        >
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
