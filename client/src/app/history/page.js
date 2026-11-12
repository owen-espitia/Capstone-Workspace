"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

const PAGE_SIZE = 24;

function formatDate(iso) {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default function HistoryPage() {
  const router = useRouter();
  const [items, setItems] = useState([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  const loadPage = useCallback(
    async (offset) => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(
          `/api/history?limit=${PAGE_SIZE}&offset=${offset}`,
          { credentials: "include", cache: "no-store" },
        );
        if (response.status === 401) {
          router.replace("/login");
          return;
        }
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Could not load history.");
        setItems((prev) => (offset === 0 ? data.items : [...prev, ...data.items]));
        setHasMore(data.has_more);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Could not load history.");
      } finally {
        setLoading(false);
      }
    },
    [router],
  );

  useEffect(() => {
    loadPage(0);
  }, [loadPage]);

  async function handleDelete(inferenceId) {
    if (!window.confirm("Delete this photo and its matches? This can't be undone.")) return;
    setDeletingId(inferenceId);
    setError(null);
    try {
      const response = await fetch(`/api/history/${inferenceId}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (!response.ok && response.status !== 404) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Could not delete this item.");
      }
      setItems((prev) => prev.filter((item) => item.inference_id !== inferenceId));
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Could not delete this item.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-8 py-12">
      <div>
        <h1 className="text-5xl">Your wardrobe</h1>
        <p className="mt-3">
          Photos you&apos;ve uploaded before, with their closest catalog matches.
        </p>
      </div>

      {error && (
        <p role="alert" className="alert-error">
          {error}
        </p>
      )}

      {!loading && !error && items.length === 0 && (
        <div className="border border-ink p-6">
          <p className="font-display text-2xl uppercase tracking-wider">Nothing here yet</p>
          <p className="mt-1 text-sm">Upload a clothing photo and it will be saved here.</p>
          <Link href="/upload" className="btn btn-primary mt-4">
            Upload image
          </Link>
        </div>
      )}

      <ul className="flex flex-col gap-6">
        {items.map((item) => (
          <li key={item.inference_id} className="border border-ink p-4">
            <div className="mb-3 flex items-center justify-between">
              <p className="eyebrow">{formatDate(item.created_at)}</p>
              <button
                onClick={() => handleDelete(item.inference_id)}
                disabled={deletingId === item.inference_id}
                className="btn btn-ghost"
              >
                {deletingId === item.inference_id ? "Deleting..." : "Delete"}
              </button>
            </div>
            <div className="grid gap-4 sm:grid-cols-4">
              <figure>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={item.image_url}
                  alt="Your upload"
                  className="aspect-square w-full border border-ink object-cover"
                />
                <figcaption className="eyebrow mt-1 text-brand">Your photo</figcaption>
              </figure>
              {item.matches.length === 0 ? (
                <p className="text-sm sm:col-span-3">No matches were stored for this photo.</p>
              ) : (
                item.matches.map((match, index) => (
                  <figure key={match.image_id}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={match.image_url}
                      alt={match.category}
                      className="aspect-square w-full border border-hairline object-cover"
                    />
                    <figcaption className="eyebrow mt-1">
                      #{index + 1} · {match.category} · {(match.similarity * 100).toFixed(1)}%
                    </figcaption>
                  </figure>
                ))
              )}
            </div>
          </li>
        ))}
      </ul>

      {loading && <p className="eyebrow">Loading...</p>}

      {hasMore && !loading && (
        <button onClick={() => loadPage(items.length)} className="btn btn-ghost self-start">
          Load more
        </button>
      )}
    </main>
  );
}
