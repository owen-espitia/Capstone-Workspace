"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

function formatDate(iso) {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function UserRow({ user }) {
  const [open, setOpen] = useState(false);
  const count = user.feedback.length;

  return (
    <li className="border border-ink p-4">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <div className="min-w-0 flex-1">
          <p className="font-display text-xl uppercase tracking-wider">
            {user.name}
            {user.is_admin && <span className="eyebrow ml-2 text-brand">Admin</span>}
          </p>
          <p className="truncate text-sm">{user.email}</p>
        </div>
        <p className="eyebrow">
          {user.upload_count} {user.upload_count === 1 ? "upload" : "uploads"}
        </p>
        {count > 0 ? (
          <button onClick={() => setOpen((value) => !value)} className="btn btn-ghost">
            {open ? "Hide" : "Show"} feedback ({count})
          </button>
        ) : (
          <p className="eyebrow">No feedback</p>
        )}
      </div>

      {open && (
        <ul className="mt-4 flex flex-col gap-3 border-t border-hairline pt-3">
          {user.feedback.map((entry) => (
            <li key={entry.inference_id}>
              <p className="eyebrow">{formatDate(entry.updated_at)}</p>
              <p className="whitespace-pre-wrap text-sm">{entry.text}</p>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export default function AdminPage() {
  const router = useRouter();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    fetch("/api/admin/users", { credentials: "include", cache: "no-store" })
      .then(async (response) => {
        if (response.status === 401) {
          router.replace("/login");
          return;
        }
        const body = await response.json().catch(() => ({}));
        if (response.status === 403) throw new Error("You don't have access to this page.");
        if (!response.ok) throw new Error(body.detail || "Could not load users.");
        setData(body);
      })
      .catch((loadError) =>
        setError(loadError instanceof Error ? loadError.message : "Could not load users."),
      );
  }, [router]);

  const visibleUsers = useMemo(() => {
    if (!data) return [];
    const needle = query.trim().toLowerCase();
    if (!needle) return data.users;
    return data.users.filter(
      (user) =>
        user.name.toLowerCase().includes(needle) || user.email.toLowerCase().includes(needle),
    );
  }, [data, query]);

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-8 py-12">
      <div>
        <h1 className="text-5xl">Admin</h1>
        <p className="mt-3">Registered users, how much they&apos;ve uploaded, and what they&apos;ve said.</p>
        {data && (
          <p className="eyebrow mt-2">
            {data.total_users} {data.total_users === 1 ? "user" : "users"} · {data.total_uploads}{" "}
            total uploads
          </p>
        )}
      </div>

      {error && (
        <div>
          <p role="alert" className="alert-error">
            {error}
          </p>
          <Link href="/" className="btn btn-ghost mt-4">
            Back home
          </Link>
        </div>
      )}

      {!data && !error && <p className="eyebrow">Loading...</p>}

      {data && (
        <>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by name or email"
            aria-label="Search users"
            className="field"
          />
          {visibleUsers.length === 0 ? (
            <p className="text-sm">No users match.</p>
          ) : (
            <ul className="flex flex-col gap-4">
              {visibleUsers.map((user) => (
                <UserRow key={user.id} user={user} />
              ))}
            </ul>
          )}
        </>
      )}
    </main>
  );
}
