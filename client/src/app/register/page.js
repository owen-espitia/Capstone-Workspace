"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({ user_name: "", user_email: "", password: "", confirm: "" });
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  function handleChange(e) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (form.password !== form.confirm) {
      setError("Passwords do not match");
      return;
    }
    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_name: form.user_name,
          user_email: form.user_email,
          password: form.password,
        }),
        credentials: "include",
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Registration failed");
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
        <h1 className="text-5xl">Create account</h1>
        <p className="mt-2 text-sm">
          Already have an account?{" "}
          <Link href="/login" className="text-brand underline underline-offset-4">
            Sign in
          </Link>
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <label htmlFor="user_name" className="label">Name</label>
          <input
            id="user_name"
            name="user_name"
            type="text"
            required
            autoComplete="name"
            value={form.user_name}
            onChange={handleChange}
            className="field"
          />
        </div>

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
            minLength={8}
            autoComplete="new-password"
            value={form.password}
            onChange={handleChange}
            className="field"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="confirm" className="label">Confirm password</label>
          <input
            id="confirm"
            name="confirm"
            type="password"
            required
            autoComplete="new-password"
            value={form.confirm}
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
          {loading ? "Creating account…" : "Create account"}
        </button>
      </form>
    </main>
  );
}
